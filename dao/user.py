from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select, update

from core.dao import BaseDAO
from models import User
from models.user import UserRole


class UserDAO(BaseDAO):
    """DAO for User model."""

    async def create(
        self,
        *,
        name: str,
        surname: str,
        email: str,
        password: str,
        role: UserRole,
        phone_number: str | None = None,
        position: str | None = None,
        place_of_work: str | None = None,
    ) -> User:
        """Create a new user.

        Args:
            name: User name.
            surname: User surname.
            email: User email.
            password: User password.
            role: User role.
            phone_number: User phone number (optional).
            position: User position (optional).
            place_of_work: User place of work (optional).

        Returns:
            User: User instance.

        """
        user = User(
            name=name,
            surname=surname,
            email=email,
            password=password,
            role=role,
            phone_number=phone_number,
            position=position,
            place_of_work=place_of_work,
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email.

        Args:
            email: User email address.

        Returns:
            User | None: User instance or None if not found.

        """
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        """Get user by id.

        Args:
            user_id: User ID.

        Returns:
            User | None: User instance or None if not found.

        """
        stmt = select(User).where(User.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_by_id(
        self,
        user_id: int,
        *,
        name: str | None = None,
        surname: str | None = None,
        email: str | None = None,
    ) -> User | None:
        """Update user by id.

        Args:
            user_id: User ID.
            name: New name (optional).
            surname: New surname (optional).
            email: New email (optional).

        Returns:
            User | None: Updated user instance or None if not found.

        """
        update_values = {}
        if name is not None:
            update_values['name'] = name
        if surname is not None:
            update_values['surname'] = surname
        if email is not None:
            update_values['email'] = email

        if not update_values:
            return await self.get_by_id(user_id)

        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(**update_values)
            .returning(User)
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_profile_fields_by_id(
        self,
        user_id: int,
        *,
        name: str | None = None,
        surname: str | None = None,
        email: str | None = None,
        phone_number: str | None = None,
        position: str | None = None,
        place_of_work: str | None = None,
    ) -> User | None:
        """Update user profile fields by id (phone, position, place_of_work).

        Args:
            user_id: User ID.
            name: New name (optional).
            surname: New surname (optional).
            email: New email (optional).
            phone_number: New phone number (optional).
            position: New position (optional).
            place_of_work: New place of work (optional).

        Returns:
            User | None: Updated user instance or None if not found.

        """
        update_values = {}
        if name is not None:
            update_values['name'] = name
        if surname is not None:
            update_values['surname'] = surname
        if email is not None:
            update_values['email'] = email
        if phone_number is not None:
            update_values['phone_number'] = phone_number
        if position is not None:
            update_values['position'] = position
        if place_of_work is not None:
            update_values['place_of_work'] = place_of_work

        if not update_values:
            return await self.get_by_id(user_id)

        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(**update_values)
            .returning(User)
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_password(
        self,
        user_id: int,
        password: str,
    ) -> User | None:
        """Update user password by id.

        Args:
            user_id: User ID.
            password: New hashed password.

        Returns:
            User | None: Updated user instance or None if not found.

        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(password=password)
            .returning(User)
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_last_login(self, user_id: int) -> User | None:
        """Update last login timestamp for a user.

        Args:
            user_id: User ID.

        Returns:
            User | None: Updated user instance or None if not found.

        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(last_login=datetime.now(UTC))
            .returning(User)
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_avatar_key(
        self,
        user_id: int,
        avatar_key: str | None,
    ) -> User | None:
        """Update user avatar key by id.

        Args:
            user_id: User ID.
            avatar_key: S3 key for avatar image (None to remove avatar).

        Returns:
            User | None: Updated user instance or None if not found.

        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(avatar_key=avatar_key)
            .returning(User)
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_by_id(self, user_id: int) -> User | None:
        """Delete user by id.

        Args:
            user_id: User ID.

        Returns:
            User | None: Deleted user instance or None if not found.

        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(is_active=False, deleted_at=datetime.now(UTC))
            .returning(User)
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def activate_by_id(self, user_id: int) -> User | None:
        """Activate a user by id.

        Sets ``is_active = True`` and clears ``deleted_at`` for the given user.

        Args:
            user_id: User ID.

        Returns:
            User | None: Activated user instance or None if not found.

        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(is_active=True, deleted_at=None)
            .returning(User)
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    def _build_filter_stmt(
        self,
        *,
        search: str | None = None,
        roles: list[UserRole] | None = None,
    ) -> Select[Any]:
        """Build base filter statement for users.

        Args:
            search: Search term for user name, surname, or email.
            roles: List of user roles to filter by.

        Returns:
            Select: SQLAlchemy select statement with filters applied.

        """
        stmt = select(User)

        if search:
            search_pattern = f'%{search}%'
            stmt = stmt.where(
                or_(
                    User.name.ilike(search_pattern),
                    User.surname.ilike(search_pattern),
                    User.email.ilike(search_pattern),
                )
            )

        if roles:
            stmt = stmt.where(User.role.in_(roles))

        return stmt

    async def count_all(
        self,
        *,
        search: str | None = None,
        roles: list[UserRole] | None = None,
    ) -> int:
        """Count all users with filters.

        Args:
            search: Search term for user name, surname, or email.
            roles: List of user roles to filter by.

        Returns:
            int: Total count of users.

        """
        stmt = self._build_filter_stmt(search=search, roles=roles)
        stmt = select(func.count()).select_from(stmt.subquery())
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def get_all(
        self,
        *,
        offset: int = 0,
        limit: int = 8,
        search: str | None = None,
        roles: list[UserRole] | None = None,
    ) -> list[User]:
        """Get all users with pagination and filters.

        Args:
            offset: Number of items to skip.
            limit: Maximum number of items to return.
            search: Search term for user name, surname, or email.
            roles: List of user roles to filter by.

        Returns:
            list[User]: List of users.

        """
        stmt = self._build_filter_stmt(search=search, roles=roles)
        stmt = (
            stmt.order_by(User.created_at.desc(), User.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_admins(
        self,
        *,
        limit: int = 3,
    ) -> list[User]:
        """Get most recently registered admin users.

        Args:
            limit: Maximum number of admin users to return.

        Returns:
            list[User]: List of admin users ordered by creation date.

        """
        stmt = (
            select(User)
            .where(
                User.is_active.is_(True),
                User.role == UserRole.ADMIN,
            )
            .order_by(User.created_at.desc(), User.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_admins(self, limit: int = 100) -> list[User]:
        """Get all admin users.

        Args:
            limit: Maximum number of admin users to return.

        Returns:
            list[User]: List of admin users ordered by creation date.

        """
        stmt = (
            select(User)
            .where(
                User.is_active.is_(True),
                User.role == UserRole.ADMIN,
            )
            .order_by(User.created_at.desc(), User.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def deactivate_unapproved_providers(
        self,
        cutoff_date: datetime,
    ) -> int:
        """Deactivate providers whose last_approved_at is before the cutoff date.

        Args:
            cutoff_date: Timestamp before which providers are deactivated.

        Returns:
            int: Number of deactivated users.

        """
        stmt = (
            update(User)
            .where(
                User.role == UserRole.PROVIDER,
                User.is_active.is_(True),
                User.last_approved_at < cutoff_date,
            )
            .values(is_active=False, deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return result.rowcount

