"""Service for fax intake and management."""

import io
import logging
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.service import BaseService
from dao import IncomingFaxDAO
from exceptions import FaxNotFoundException
from models.incoming_fax import FaxDirection, FaxStatus, IncomingFax
from schemas.fax import (
    IncomingFaxListResponseSchema,
    IncomingFaxResponseSchema,
)
from services.aws.actions import S3Actions, generate_storage_key
from services.fax.ringcentral_client import RingCentralClient

logger = logging.getLogger(__name__)

FAX_STORAGE_PREFIX = 'faxes/inbound'


@lru_cache(maxsize=1)
def _get_shared_ringcentral_client() -> RingCentralClient:
    """Get a process-wide RingCentralClient singleton.

    RingCentralClient owns an httpx.AsyncClient connection pool that is
    never explicitly closed, so it must not be re-created per request -
    FaxService is instantiated fresh on every request via get_service().
    """
    return RingCentralClient()


def extract_fax_message_ids(payload: dict[str, Any]) -> list[str]:
    """Extract new fax message IDs from a RingCentral webhook payload.

    RingCentral message-store push notifications group changes by
    message type (Fax, SMS, Voicemail, etc.); only the "Fax" bucket's
    message IDs are relevant here.

    Args:
        payload: Parsed JSON body of the webhook request.

    Returns:
        list[str]: Message IDs for new/updated fax messages.

    """
    changes = payload.get('body', {}).get('changes', [])
    message_ids: list[str] = []
    for change in changes:
        if change.get('type') != 'Fax':
            continue
        message_ids.extend(str(mid) for mid in change.get('ids', []))
    return message_ids


class FaxService(BaseService):
    """Service for fax intake, storage, and matching."""

    def __init__(
        self,
        db_session: AsyncSession,
        *,
        fax_dao: IncomingFaxDAO | None = None,
        s3_actions: S3Actions | None = None,
        ringcentral_client: RingCentralClient | None = None,
    ) -> None:
        """Initialize FaxService.

        Args:
            db_session: Database session.
            fax_dao: Optional IncomingFaxDAO instance.
            s3_actions: Optional S3Actions instance.
            ringcentral_client: Optional RingCentralClient instance.

        """
        super().__init__(db_session)
        self._fax_dao = fax_dao or IncomingFaxDAO(db_session)
        self._s3_actions = s3_actions or S3Actions()
        self._ringcentral_client = (
            ringcentral_client or _get_shared_ringcentral_client()
        )

    async def process_webhook_payload(
        self,
        payload: dict[str, Any],
    ) -> list[IncomingFax]:
        """Process a RingCentral fax webhook notification payload.

        Extracts new fax message IDs and processes each one. A failure
        processing one message does not prevent the others from being
        processed, since RingCentral may batch several new messages into
        a single webhook delivery.

        Args:
            payload: Parsed JSON body of the webhook request.

        Returns:
            list[IncomingFax]: Faxes created or found for this payload.

        """
        message_ids = extract_fax_message_ids(payload)
        if not message_ids:
            logger.info('Fax webhook payload had no new fax message IDs')
            return []

        results: list[IncomingFax] = []
        for message_id in message_ids:
            try:
                fax = await self.process_inbound_message(message_id)
            except Exception:
                logger.exception(
                    'Failed to process inbound fax message %s', message_id
                )
                continue
            if fax:
                results.append(fax)
        return results

    async def process_inbound_message(
        self,
        message_id: str,
    ) -> IncomingFax | None:
        """Download and store a single inbound fax message.

        Idempotent: if a fax with this provider_message_id already
        exists (e.g. RingCentral redelivered the same webhook event),
        the existing record is returned without reprocessing.

        Args:
            message_id: RingCentral message ID.

        Returns:
            IncomingFax | None: The stored (or pre-existing) fax record.

        """
        existing = await self._fax_dao.get_by_provider_message_id(
            message_id
        )
        if existing:
            logger.info(
                'Fax message %s already processed (fax id=%s), skipping',
                message_id,
                existing.id,
            )
            return existing

        message = await self._ringcentral_client.get_message(message_id)
        from_number = message.get('from', {}).get('phoneNumber')
        to_recipients = message.get('to', [])
        to_number = (
            to_recipients[0].get('phoneNumber') if to_recipients else None
        )
        page_count = message.get('faxPageCount') or message.get('pages')

        attachment = self._ringcentral_client.get_document_attachment(
            message
        )
        if not attachment:
            logger.warning(
                'Fax message %s has no document attachment', message_id
            )
            fax = await self._fax_dao.create(
                provider_message_id=message_id,
                direction=FaxDirection.INBOUND,
                status=FaxStatus.FAILED,
                from_number=from_number,
                to_number=to_number,
                page_count=page_count,
            )
            await self._session.commit()
            return fax

        content, content_type = (
            await self._ringcentral_client.download_attachment(
                message_id=message_id,
                attachment_id=str(attachment['id']),
            )
        )

        extension = '.pdf' if content_type == 'application/pdf' else '.tiff'
        s3_key = generate_storage_key(
            prefix=FAX_STORAGE_PREFIX,
            file_extension=extension,
        )
        self._s3_actions.upload_to_s3(
            s3_key,
            io.BytesIO(content),
            content_type,
            metadata={'ringcentral_message_id': message_id},
        )

        fax = await self._fax_dao.create(
            provider_message_id=message_id,
            direction=FaxDirection.INBOUND,
            status=FaxStatus.RECEIVED,
            from_number=from_number,
            to_number=to_number,
            page_count=page_count,
            s3_key=s3_key,
            content_type=content_type,
            file_size=len(content),
        )
        await self._session.commit()
        logger.info(
            'Stored inbound fax %s (message_id=%s) from %s',
            fax.id,
            message_id,
            from_number,
        )
        return fax

    async def get_fax(self, fax_id: int) -> IncomingFaxResponseSchema:
        """Get a fax by ID, with a presigned download URL.

        Args:
            fax_id: ID of the fax.

        Returns:
            IncomingFaxResponseSchema: Fax details with download URL.

        Raises:
            FaxNotFoundException: If the fax does not exist.

        """
        fax = await self._fax_dao.get_by_id(fax_id)
        if not fax:
            raise FaxNotFoundException

        download_url = None
        if fax.s3_key:
            download_url = self._s3_actions.get_presigned_url(key=fax.s3_key)

        return IncomingFaxResponseSchema.model_validate(fax).model_copy(
            update={'download_url': download_url}
        )

    async def list_faxes(
        self,
        *,
        page: int = 1,
        limit: int = 20,
        status: FaxStatus | None = None,
    ) -> IncomingFaxListResponseSchema:
        """List faxes with pagination, optionally filtered by status.

        Args:
            page: 1-based page number.
            limit: Maximum number of items per page.
            status: Optional status to filter by.

        Returns:
            IncomingFaxListResponseSchema: Paginated list of faxes.

        """
        offset = max(0, page - 1) * limit
        faxes, total = await self._fax_dao.get_all(
            offset=offset, limit=limit, status=status
        )
        items = [
            IncomingFaxResponseSchema.model_validate(fax) for fax in faxes
        ]
        total_pages = max(1, (total + limit - 1) // limit)
        return IncomingFaxListResponseSchema(
            items=items,
            page=page,
            total=total,
            showing=len(items),
            total_pages=total_pages,
        )

    async def send_outbound_fax(
        self,
        *,
        to_number: str,
        attachments: list[tuple[str, bytes, str]],
        request_id: int | None = None,
        cover_page_text: str | None = None,
    ) -> IncomingFax:
        """Send an outbound fax via RingCentral and record it.

        Args:
            to_number: Destination fax number.
            attachments: List of (filename, content, content_type) tuples.
                At least one attachment is required.
            request_id: Ambulance request this fax relates to, if any.
            cover_page_text: Optional cover page text.

        Returns:
            IncomingFax: Created outbound fax record.

        Raises:
            FaxProviderException: If the send request fails.

        """
        result = await self._ringcentral_client.send_fax(
            to_number=to_number,
            attachments=attachments,
            cover_page_text=cover_page_text,
        )
        provider_message_id = str(result['id'])
        message_status = str(result.get('messageStatus', '')).lower()
        status = (
            FaxStatus.SENT if message_status == 'sent' else FaxStatus.QUEUED
        )

        fax = await self._fax_dao.create(
            provider_message_id=provider_message_id,
            direction=FaxDirection.OUTBOUND,
            status=status,
            to_number=to_number,
            page_count=result.get('faxPageCount') or result.get('pages'),
            request_id=request_id,
        )
        await self._session.commit()
        logger.info(
            'Sent outbound fax %s (message_id=%s) to %s',
            fax.id,
            provider_message_id,
            to_number,
        )
        return fax

    async def link_fax_to_request(
        self,
        *,
        fax_id: int,
        request_id: int,
        matched_by_user_id: int,
    ) -> IncomingFaxResponseSchema:
        """Manually link an unresolved fax to an ambulance request.

        Args:
            fax_id: ID of the fax to link.
            request_id: ID of the ambulance request to link to.
            matched_by_user_id: ID of the admin user performing the link.

        Returns:
            IncomingFaxResponseSchema: Updated fax.

        Raises:
            FaxNotFoundException: If the fax does not exist.

        """
        fax = await self._fax_dao.link_to_request(
            fax_id=fax_id,
            request_id=request_id,
            matched_by_user_id=matched_by_user_id,
        )
        if not fax:
            raise FaxNotFoundException
        await self._session.commit()
        return IncomingFaxResponseSchema.model_validate(fax)
