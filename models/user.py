from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, String, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models import BaseIdMixin, BaseTimeStampMixin, SoftDelete

if TYPE_CHECKING:
    from models import Organization


class UserRole(StrEnum):
    """Enumeration of user roles in the system."""

    ADMIN = 'admin'
    PROVIDER = 'provider'


class User(BaseIdMixin, BaseTimeStampMixin, SoftDelete):
    """User model represents a system user.

    Fields:
    - name: First name of the user.
    - surname: Last name of the user.
    - email: Unique email for login and contact.
    - password: Hashed password of the user.
    - role: User role (admin or provider).
    - is_active: Indicates if user is active.
    """

    __tablename__ = 'users'

    name: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment='First name of the user',
    )
    surname: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment='Last name of the user',
    )
    email: Mapped[str] = mapped_column(
        String(254),
        nullable=False,
        unique=True,
        comment='Unique email address for login',
    )
    password: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment='Hashed password',
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole),
        nullable=False,
        server_default='PROVIDER',
        comment='Role of the user: admin or provider',
    )
    phone_number: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment='Phone number of the user'
    )
    position: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment='Position of the user'
    )
    place_of_work: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment='Place of work of the user'
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment='Date and time of last login',
    )
    avatar_key: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment='S3 key for user avatar image',
    )
    last_approved_at = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # Relationships
    organization: Mapped['Organization | None'] = relationship(
        'Organization',
        back_populates='user',
        uselist=False,
    )

    def __repr__(self) -> str:
        """Return a string representation of the user."""
        return f'<User {self.email}>'
