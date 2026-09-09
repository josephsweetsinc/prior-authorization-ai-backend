from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from core.dao import BaseDAO
from models.incoming_fax import FaxDirection, FaxStatus, IncomingFax


class IncomingFaxDAO(BaseDAO):
    """DAO for IncomingFax model."""

    async def create(
        self,
        *,
        provider_message_id: str,
        direction: FaxDirection = FaxDirection.INBOUND,
        status: FaxStatus = FaxStatus.RECEIVED,
        from_number: str | None = None,
        to_number: str | None = None,
        page_count: int | None = None,
        s3_key: str | None = None,
        content_type: str | None = None,
        file_size: int | None = None,
        request_id: int | None = None,
    ) -> IncomingFax:
        """Create a new incoming fax record.

        Args:
            provider_message_id: Fax provider's message ID (idempotency key).
            direction: Fax direction (default: inbound).
            status: Initial processing status (default: received).
            from_number: Sender fax number.
            to_number: Recipient fax number.
            page_count: Number of pages in the fax.
            s3_key: S3 object key of the stored document.
            content_type: MIME type of the stored document.
            file_size: Size of the stored document in bytes.
            request_id: Ambulance request this fax relates to, if known
                at creation time (used for outbound fax records).

        Returns:
            IncomingFax: Created fax instance.

        """
        fax = IncomingFax(
            provider_message_id=provider_message_id,
            direction=direction,
            status=status,
            from_number=from_number,
            to_number=to_number,
            page_count=page_count,
            s3_key=s3_key,
            content_type=content_type,
            file_size=file_size,
            request_id=request_id,
        )
        self._session.add(fax)
        await self._session.flush()
        await self._session.refresh(fax)
        return fax

    async def get_by_provider_message_id(
        self,
        provider_message_id: str,
    ) -> IncomingFax | None:
        """Get a fax by its provider message ID.

        Used to detect and skip duplicate webhook deliveries for the
        same fax message.

        Args:
            provider_message_id: Fax provider's message ID.

        Returns:
            IncomingFax | None: Matching fax, or None if not found.

        """
        stmt = select(IncomingFax).where(
            IncomingFax.provider_message_id == provider_message_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, fax_id: int) -> IncomingFax | None:
        """Get a fax by ID.

        Args:
            fax_id: ID of the fax.

        Returns:
            IncomingFax | None: Matching fax, or None if not found.

        """
        stmt = (
            select(IncomingFax)
            .options(selectinload(IncomingFax.request))
            .where(IncomingFax.id == fax_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        status: FaxStatus | None = None,
        direction: FaxDirection | None = None,
    ) -> tuple[list[IncomingFax], int]:
        """Get paginated faxes, optionally filtered by status/direction.

        Args:
            offset: Number of items to skip.
            limit: Maximum number of items to return.
            status: Optional status to filter by.
            direction: Optional direction to filter by.

        Returns:
            Tuple of (list of faxes, total count matching the filters).

        """
        stmt = select(IncomingFax)
        count_stmt = select(func.count()).select_from(IncomingFax)

        if status is not None:
            stmt = stmt.where(IncomingFax.status == status)
            count_stmt = count_stmt.where(IncomingFax.status == status)
        if direction is not None:
            stmt = stmt.where(IncomingFax.direction == direction)
            count_stmt = count_stmt.where(IncomingFax.direction == direction)

        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            stmt.order_by(IncomingFax.created_at.desc(), IncomingFax.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def link_to_request(
        self,
        *,
        fax_id: int,
        request_id: int,
        matched_by_user_id: int | None,
    ) -> IncomingFax | None:
        """Link a fax to an ambulance request and mark it matched.

        Args:
            fax_id: ID of the fax to link.
            request_id: ID of the ambulance request to link to.
            matched_by_user_id: ID of the user performing the link, if a
                human is doing the linking (None for automated matches).

        Returns:
            IncomingFax | None: Updated fax, or None if not found.

        """
        fax = await self.get_by_id(fax_id)
        if not fax:
            return None
        fax.request_id = request_id
        fax.matched_by_user_id = matched_by_user_id
        fax.status = FaxStatus.MATCHED
        await self._session.flush()
        await self._session.refresh(fax)
        return fax
