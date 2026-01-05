from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models import BaseIdMixin, BaseTimeStampMixin, SoftDelete


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

    @property
    def full_name(self) -> str:
        """Return full name of the user."""
        return f'{self.name} {self.surname}'

    def __repr__(self) -> str:
        """Return a string representation of the user."""
        return f'<User {self.email}>'
