"""Tests for IncomingFaxDAO."""

import pytest

from dao import IncomingFaxDAO
from models.incoming_fax import FaxDirection, FaxStatus


@pytest.fixture
def fax_dao(db_session):
    """Create IncomingFaxDAO instance."""
    return IncomingFaxDAO(db_session)


class TestIncomingFaxDAO:
    """Test suite for IncomingFaxDAO."""

    @pytest.mark.asyncio
    async def test_create_and_get_by_provider_message_id(
        self, fax_dao, db_session
    ):
        """Test creating a fax and retrieving it by provider message ID."""
        fax = await fax_dao.create(
            provider_message_id='rc-123',
            from_number='+15551234567',
            to_number='+15557654321',
            page_count=2,
            s3_key='faxes/inbound/2026/09/08/abc.pdf',
            content_type='application/pdf',
            file_size=1024,
        )
        await db_session.commit()

        assert fax.id is not None
        assert fax.status == FaxStatus.RECEIVED
        assert fax.direction == FaxDirection.INBOUND

        found = await fax_dao.get_by_provider_message_id('rc-123')
        assert found is not None
        assert found.id == fax.id

    @pytest.mark.asyncio
    async def test_get_by_provider_message_id_not_found(self, fax_dao):
        """Test that a missing provider message ID returns None."""
        found = await fax_dao.get_by_provider_message_id('does-not-exist')
        assert found is None

    @pytest.mark.asyncio
    async def test_get_all_filters_by_status(self, fax_dao, db_session):
        """Test that get_all filters faxes by status."""
        await fax_dao.create(
            provider_message_id='rc-1', status=FaxStatus.RECEIVED
        )
        await fax_dao.create(
            provider_message_id='rc-2', status=FaxStatus.UNRESOLVED
        )
        await db_session.commit()

        faxes, total = await fax_dao.get_all(status=FaxStatus.UNRESOLVED)

        assert total == 1
        assert len(faxes) == 1
        assert faxes[0].provider_message_id == 'rc-2'

    @pytest.mark.asyncio
    async def test_get_all_pagination(self, fax_dao, db_session):
        """Test that get_all paginates results correctly."""
        for i in range(5):
            await fax_dao.create(provider_message_id=f'rc-{i}')
        await db_session.commit()

        faxes, total = await fax_dao.get_all(offset=0, limit=2)
        assert total == 5
        assert len(faxes) == 2

    @pytest.mark.asyncio
    async def test_link_to_request(
        self, fax_dao, db_session, user_factory, ambulance_request_factory
    ):
        """Test linking a fax to an ambulance request."""
        user = await user_factory()
        request = await ambulance_request_factory(user_id=user.id)
        fax = await fax_dao.create(provider_message_id='rc-link')
        await db_session.commit()

        updated = await fax_dao.link_to_request(
            fax_id=fax.id,
            request_id=request.id,
            matched_by_user_id=user.id,
        )
        await db_session.commit()

        assert updated is not None
        assert updated.status == FaxStatus.MATCHED
        assert updated.request_id == request.id
        assert updated.matched_by_user_id == user.id

    @pytest.mark.asyncio
    async def test_link_to_request_not_found(self, fax_dao):
        """Test that linking a nonexistent fax returns None."""
        result = await fax_dao.link_to_request(
            fax_id=999999,
            request_id=1,
            matched_by_user_id=1,
        )
        assert result is None
