from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models import BaseIdMixin, BaseTimeStampMixin, SoftDelete

if TYPE_CHECKING:
    from models.ambulance_request import AmbulanceRequest
    from models.user import User


class FaxDirection(StrEnum):
    """Enumeration of fax directions."""

    INBOUND = 'inbound'
    OUTBOUND = 'outbound'


class FaxStatus(StrEnum):
    """Enumeration of fax processing statuses.

    - RECEIVED: Fax content downloaded and stored, not yet linked.
    - PROCESSING: AI matching/extraction in progress.
    - MATCHED: Automatically or manually linked to an ambulance request.
    - UNRESOLVED: Could not be confidently matched; needs manual review.
    - FAILED: Download, storage, or processing failed.
    """

    RECEIVED = 'received'
    PROCESSING = 'processing'
    MATCHED = 'matched'
    UNRESOLVED = 'unresolved'
    FAILED = 'failed'


class IncomingFax(BaseIdMixin, BaseTimeStampMixin, SoftDelete):
    """Fax intake/log model.

    Fields:
    - direction: Inbound or outbound (only inbound is populated so far).
    - status: Current processing status.
    - provider_message_id: Fax provider's (RingCentral) message ID; used
      to prevent double-processing the same webhook event.
    - from_number: Sender fax number.
    - to_number: Recipient fax number (our RingCentral fax line).
    - page_count: Number of pages in the fax, if known.
    - s3_key: S3 object key of the stored fax document.
    - content_type: MIME type of the stored document.
    - file_size: Size of the stored document in bytes.
    - request_id: Linked ambulance request, once matched.
    - matched_by_user_id: User who manually linked this fax, if applicable.
    """

    __tablename__ = 'incoming_faxes'

    direction: Mapped[FaxDirection] = mapped_column(
        SAEnum(FaxDirection),
        nullable=False,
        server_default='INBOUND',
        comment='Fax direction (inbound/outbound)',
    )
    status: Mapped[FaxStatus] = mapped_column(
        SAEnum(FaxStatus),
        nullable=False,
        server_default='RECEIVED',
        index=True,
        comment='Current processing status of the fax',
    )
    provider_message_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment=(
            "Fax provider's message ID, used to prevent duplicate "
            'processing of the same webhook event'
        ),
    )
    from_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment='Sender fax number',
    )
    to_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment='Recipient fax number',
    )
    page_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment='Number of pages in the fax',
    )
    s3_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment='S3 object key of the stored fax document',
    )
    content_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment='MIME type of the stored document',
    )
    file_size: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment='Size of the stored document in bytes',
    )
    request_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('ambulance_requests.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
        comment='Linked ambulance request, once matched',
    )
    matched_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        comment='User who manually linked this fax, if applicable',
    )

    # Relationships
    request: Mapped['AmbulanceRequest | None'] = relationship(
        'AmbulanceRequest',
    )
    matched_by_user: Mapped['User | None'] = relationship(
        'User',
    )

    def __repr__(self) -> str:
        """Return a string representation of the fax."""
        return f'<IncomingFax {self.id} - {self.status}>'
