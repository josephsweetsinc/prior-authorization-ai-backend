from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy import (
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models import BaseIdMixin, BaseTimeStampMixin

if TYPE_CHECKING:
    from models.ambulance_request import AmbulanceRequest
    from models.user import User


class PHIAccessAction(StrEnum):
    """Enumeration of PHI-access actions tracked for audit purposes.

    Distinct from RequestStatusHistory, which tracks status *changes*.
    This tracks reads of PHI-bearing data: opening a request's detail
    view, or downloading one of its generated documents.
    """

    VIEW = 'view'
    DOWNLOAD_NOVITAS_PACKAGE = 'download_novitas_package'
    DOWNLOAD_CALL_SHEET = 'download_call_sheet'
    DOWNLOAD_CMS1500 = 'download_cms1500'


class RequestAccessLog(BaseIdMixin, BaseTimeStampMixin):
    """Audit log of PHI access on an ambulance request.

    Fields:
    - request_id: ID of the ambulance request that was accessed.
    - user_id: ID of the user who accessed it, if known.
    - action: What kind of access this was (enum).
    """

    __tablename__ = 'request_access_logs'

    request_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('ambulance_requests.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='ID of the ambulance request that was accessed',
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        comment='ID of the user who accessed it, if known',
    )
    action: Mapped[PHIAccessAction] = mapped_column(
        SAEnum(PHIAccessAction),
        nullable=False,
        comment='What kind of PHI access this was',
    )

    # Relationships
    request: Mapped['AmbulanceRequest'] = relationship(
        'AmbulanceRequest',
    )
    user: Mapped['User | None'] = relationship(
        'User',
    )

    def __repr__(self) -> str:
        """Return a string representation of the access log entry."""
        return (
            f'<RequestAccessLog {self.id} - '
            f'Request {self.request_id} - {self.action}>'
        )
