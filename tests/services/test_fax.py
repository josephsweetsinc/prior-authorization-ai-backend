"""Tests for FaxService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dao import IncomingFaxDAO
from exceptions import FaxNotFoundException
from models.incoming_fax import FaxDirection, FaxStatus
from services.fax.fax_service import (
    FaxService,
    _get_shared_ringcentral_client,
    extract_fax_message_ids,
)
from services.fax.ringcentral_client import RingCentralClient


class TestExtractFaxMessageIds:
    """Test suite for extract_fax_message_ids()."""

    def test_extracts_fax_ids_only(self):
        """Test that only IDs from the 'Fax' change bucket are returned."""
        payload = {
            'body': {
                'changes': [
                    {'type': 'SMS', 'ids': ['sms-1']},
                    {'type': 'Fax', 'ids': ['fax-1', 'fax-2']},
                ]
            }
        }
        assert extract_fax_message_ids(payload) == ['fax-1', 'fax-2']

    def test_no_changes_returns_empty(self):
        """Test that a payload with no changes returns an empty list."""
        assert extract_fax_message_ids({'body': {}}) == []
        assert extract_fax_message_ids({}) == []


class TestSharedRingCentralClient:
    """Test suite for _get_shared_ringcentral_client()."""

    def test_returns_same_instance(self):
        """Test that the same RingCentralClient instance is reused, so
        its underlying httpx connection pool isn't re-created per
        request.
        """  # noqa: D205
        assert (
            _get_shared_ringcentral_client()
            is _get_shared_ringcentral_client()
        )


class TestFaxService:
    """Test suite for FaxService."""

    @pytest.fixture
    def mock_s3_actions(self) -> MagicMock:
        """Create mock S3Actions."""
        mock = MagicMock()
        mock.get_presigned_url.return_value = (
            'https://s3.example.com/presigned-url'
        )
        return mock

    @pytest.fixture
    def mock_ringcentral_client(self) -> MagicMock:
        """Create mock RingCentralClient."""
        mock = MagicMock(spec=RingCentralClient)
        mock.get_message = AsyncMock(
            return_value={
                'from': {'phoneNumber': '+15551234567'},
                'to': [{'phoneNumber': '+15557654321'}],
                'faxPageCount': 2,
                'attachments': [
                    {'id': 'att-1', 'contentType': 'application/pdf'}
                ],
            }
        )
        mock.get_document_attachment = MagicMock(
            side_effect=RingCentralClient.get_document_attachment
        )
        mock.download_attachment = AsyncMock(
            return_value=(b'%PDF-1.4 fake content', 'application/pdf')
        )
        return mock

    @pytest.fixture
    def service(
        self,
        db_session,
        mock_s3_actions,
        mock_ringcentral_client,
    ) -> FaxService:
        """Create FaxService instance with mocks."""
        return FaxService(
            db_session=db_session,
            fax_dao=IncomingFaxDAO(db_session),
            s3_actions=mock_s3_actions,
            ringcentral_client=mock_ringcentral_client,
        )

    @pytest.mark.asyncio
    async def test_process_inbound_message_success(
        self, service, mock_s3_actions, mock_ringcentral_client
    ):
        """Test successfully processing a new inbound fax message."""
        fax = await service.process_inbound_message('rc-msg-1')

        assert fax is not None
        assert fax.status == FaxStatus.RECEIVED
        assert fax.from_number == '+15551234567'
        assert fax.to_number == '+15557654321'
        assert fax.page_count == 2
        assert fax.file_size == len(b'%PDF-1.4 fake content')
        mock_s3_actions.upload_to_s3.assert_called_once()
        mock_ringcentral_client.download_attachment.assert_awaited_once_with(
            message_id='rc-msg-1', attachment_id='att-1'
        )

    @pytest.mark.asyncio
    async def test_process_inbound_message_idempotent(
        self, service, mock_ringcentral_client
    ):
        """Test that reprocessing the same message ID is a no-op."""
        first = await service.process_inbound_message('rc-msg-dup')
        mock_ringcentral_client.get_message.reset_mock()

        second = await service.process_inbound_message('rc-msg-dup')

        assert second.id == first.id
        mock_ringcentral_client.get_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_inbound_message_no_attachment(
        self, service, mock_ringcentral_client
    ):
        """Test that a message with no attachments is marked FAILED."""
        mock_ringcentral_client.get_message = AsyncMock(
            return_value={
                'from': {'phoneNumber': '+15551234567'},
                'to': [],
                'attachments': [],
            }
        )

        fax = await service.process_inbound_message('rc-msg-empty')

        assert fax is not None
        assert fax.status == FaxStatus.FAILED

    @pytest.mark.asyncio
    async def test_process_inbound_message_no_attachment_commits(
        self, service, mock_ringcentral_client, db_session
    ):
        """Test that the FAILED record for a missing attachment is
        committed, not just flushed - otherwise it disappears once the
        request's session closes.
        """  # noqa: D205
        mock_ringcentral_client.get_message = AsyncMock(
            return_value={
                'from': {'phoneNumber': '+15551234567'},
                'to': [],
                'attachments': [],
            }
        )
        with patch.object(
            db_session, 'commit', wraps=db_session.commit
        ) as mock_commit:
            await service.process_inbound_message('rc-msg-empty-commit')

        mock_commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_webhook_payload_processes_all_fax_ids(
        self, service
    ):
        """Test that a webhook payload with multiple fax IDs processes all."""
        payload = {
            'body': {
                'changes': [
                    {'type': 'Fax', 'ids': ['rc-a', 'rc-b']},
                ]
            }
        }

        results = await service.process_webhook_payload(payload)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_process_webhook_payload_no_fax_changes(self, service):
        """Test that a payload with no fax changes processes nothing."""
        results = await service.process_webhook_payload(
            {'body': {'changes': [{'type': 'SMS', 'ids': ['sms-1']}]}}
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_process_webhook_payload_continues_after_one_failure(
        self, service, mock_ringcentral_client
    ):
        """Test that one failing message doesn't stop the others."""

        async def get_message_side_effect(message_id: str):
            if message_id == 'rc-bad':
                raise RuntimeError('boom')
            return {
                'from': {'phoneNumber': '+15551234567'},
                'to': [{'phoneNumber': '+15557654321'}],
                'attachments': [
                    {'id': 'att-1', 'contentType': 'application/pdf'}
                ],
            }

        mock_ringcentral_client.get_message = AsyncMock(
            side_effect=get_message_side_effect
        )

        results = await service.process_webhook_payload(
            {
                'body': {
                    'changes': [
                        {'type': 'Fax', 'ids': ['rc-bad', 'rc-good']}
                    ]
                }
            }
        )

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_fax_not_found(self, service):
        """Test that getting a nonexistent fax raises."""
        with pytest.raises(FaxNotFoundException):
            await service.get_fax(999999)

    @pytest.mark.asyncio
    async def test_get_fax_includes_download_url(
        self, service, mock_s3_actions
    ):
        """Test that get_fax includes a presigned download URL."""
        created = await service.process_inbound_message('rc-msg-url')

        result = await service.get_fax(created.id)

        assert result.download_url == 'https://s3.example.com/presigned-url'
        mock_s3_actions.get_presigned_url.assert_called_once_with(
            key=created.s3_key
        )

    @pytest.mark.asyncio
    async def test_list_faxes_pagination(self, service):
        """Test that list_faxes returns paginated results."""
        for i in range(3):
            await service.process_inbound_message(f'rc-list-{i}')

        result = await service.list_faxes(page=1, limit=2)

        assert result.total == 3
        assert result.showing == 2
        assert result.total_pages == 2

    @pytest.mark.asyncio
    async def test_link_fax_to_request_not_found(self, service):
        """Test that linking a nonexistent fax raises."""
        with pytest.raises(FaxNotFoundException):
            await service.link_fax_to_request(
                fax_id=999999,
                request_id=1,
                matched_by_user_id=1,
            )

    @pytest.mark.asyncio
    async def test_send_outbound_fax_success(
        self, service, mock_ringcentral_client
    ):
        """Test that a successful outbound send is recorded as SENT."""
        mock_ringcentral_client.send_fax = AsyncMock(
            return_value={
                'id': 'rc-out-1',
                'messageStatus': 'Sent',
                'faxPageCount': 3,
            }
        )

        fax = await service.send_outbound_fax(
            to_number='+15559990000',
            attachments=[('doc.pdf', b'%PDF-fake', 'application/pdf')],
            request_id=42,
            cover_page_text='Cover text',
        )

        assert fax.direction == FaxDirection.OUTBOUND
        assert fax.status == FaxStatus.SENT
        assert fax.to_number == '+15559990000'
        assert fax.request_id == 42
        assert fax.page_count == 3
        mock_ringcentral_client.send_fax.assert_awaited_once_with(
            to_number='+15559990000',
            attachments=[('doc.pdf', b'%PDF-fake', 'application/pdf')],
            cover_page_text='Cover text',
        )

    @pytest.mark.asyncio
    async def test_send_outbound_fax_queued_status(
        self, service, mock_ringcentral_client
    ):
        """Test that a non-'Sent' provider status is recorded as QUEUED."""
        mock_ringcentral_client.send_fax = AsyncMock(
            return_value={'id': 'rc-out-2', 'messageStatus': 'Queued'}
        )

        fax = await service.send_outbound_fax(
            to_number='+15559990000',
            attachments=[('doc.pdf', b'%PDF-fake', 'application/pdf')],
        )

        assert fax.status == FaxStatus.QUEUED
        assert fax.request_id is None
