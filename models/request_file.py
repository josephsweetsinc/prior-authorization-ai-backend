from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models import BaseIdMixin, BaseTimeStampMixin

if TYPE_CHECKING:
    from models.ambulance_request import AmbulanceRequest


class RequestFile(BaseIdMixin, BaseTimeStampMixin):
    """Request file model for storing uploaded document information.

    Fields:
    - request_id: ID of the ambulance request.
    - uploaded_by_user_id: ID of the user who uploaded the file.
    - filename: Original filename.
    - s3_key: S3 object key (path in S3 bucket).
    - file_size: File size in bytes.
    - content_type: MIME type of the file.
    - is_verification_of_medical_necessity: Cached AI content-check
      result (None until checked once).
    """

    __tablename__ = 'request_files'

    request_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('ambulance_requests.id', ondelete='CASCADE'),
        nullable=True,
        comment='ID of the ambulance request (nullable for temporary files)',
    )
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        comment=(
            'ID of the user who uploaded the file - the authorization '
            'boundary for linking an unattached file to a request; a '
            'NULL value (e.g. a pre-existing row from before this '
            'column existed) is never treated as owned by anyone'
        ),
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment='Original filename',
    )
    s3_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment='S3 object key (path in S3 bucket)',
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment='File size in bytes',
    )
    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment='MIME type of the file',
    )
    is_verification_of_medical_necessity: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment=(
            'Whether this file is a Verification of Medical Necessity '
            'document, per a one-time AI content check. NULL means not '
            'yet checked - cached so the (costly, per-file) check runs '
            'once per file rather than on every completion-status check'
        ),
    )

    # Relationships
    request: Mapped['AmbulanceRequest'] = relationship(
        'AmbulanceRequest',
        back_populates='files',
    )

    def __repr__(self) -> str:
        """Return a string representation of the file."""
        return f'<RequestFile {self.id} - {self.filename}>'
