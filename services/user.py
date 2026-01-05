from sqlalchemy.ext.asyncio import AsyncSession

from core import BaseService
from dao import UserDAO
from exceptions import UserHasNoPermissionPermission, UserNotFoundByIdException
from models import User
from models.user import UserRole
from schemas import (
    CreateUserByAdminRequestSchema,
    CreateUserRequestSchema,
    UpdateUserRequestSchema,
    UserListItemSchema,
    UserResponseShema,
)
from services.jwt.hasher import Hasher


class UserService(BaseService):
    """Service layer for managing user-related operations."""

    def __init__(
        self,
        db_session: AsyncSession,
        *,
        user_dao: UserDAO | None = None,
        hash_service: Hasher | None = None,
    ):
        """Initialize UserService.

        Args:
            db_session (AsyncSession): Database session.
            user_dao (UserDAO | None): Optional UserDAO instance.
            hash_service (Hasher | None): Optional password hasher.

        """
        super().__init__(db_session)
        self._user_dao = user_dao or UserDAO(db_session)
        self._hash_service = hash_service or Hasher()

    async def create_new_user(
        self,
        user_data: CreateUserRequestSchema | CreateUserByAdminRequestSchema,
        *,
        user_role: UserRole | None = None,
    ) -> UserResponseShema:
        """Create a new user in the database.

        Args:
            user_data (CreateUserByAdminRequestSchema): User data containing
            name, surname, email, password
            user_role (UserRole | None): User role. Only for admin create.

        Returns:
            CreateUserResponseShema: Created user information including
            ID, name, surname, email, active status, and roles

        Note:
            If roles are not provided, defaults to [UserRoles.USER]

        """
        hashed_pass: str = self._hash_service.hash_password(
            user_data.password,
        )
        role: UserRole = (
            user_role if user_role is not None else UserRole.PROVIDER
        )
        created_user: User = await self._user_dao.create(
            name=user_data.name,
            surname=user_data.surname,
            email=user_data.email,
            password=hashed_pass,
            role=role,
            phone_number=getattr(user_data, 'phone_number', None),
            position=getattr(user_data, 'position', None),
            place_of_work=getattr(user_data, 'place_of_work', None),
        )
        await self._session.commit()
        return UserResponseShema.model_validate(created_user)

    async def get_user_by_id(self, user_id: int) -> User:
        """Retrieve a user by ID.

        Args:
            user_id (int): User ID.

        Returns:
            User: Retrieved user instance.

        Raises:
            UserNotFoundByIdException: If user does not exist or is inactive.

        """
        user: User | None = await self._user_dao.get_by_id(user_id)
        if not user:
            raise UserNotFoundByIdException
        if not user.is_active:
            raise UserNotFoundByIdException
        return user

    async def update_user_by_id(
        self,
        user_id: int,
        user_data: UpdateUserRequestSchema,
    ) -> UserResponseShema:
        """Update user by id.

        Args:
            user_id: User ID.
            user_data: UpdateUserRequestSchema with fields to update.

        Returns:
            UserResponseShema: Updated user information.

        Raises:
            UserNotFoundByIdException: If user not found.

        """
        user: User | None = await self._user_dao.update_by_id(
            user_id,
            name=user_data.name,
            surname=user_data.surname,
            email=user_data.email,
        )
        await self._session.commit()
        if not user:
            raise UserNotFoundByIdException
        return UserResponseShema.model_validate(user)

    async def delete_user_by_id(
        self, current_user: User, user_id: int
    ) -> UserResponseShema:
        """Delete a user by ID.

        Args:
            current_user (User): Current authenticated user.
            user_id (int): User ID.

        Returns:
            UserResponseShema: Deleted user information.

        Raises:
            UserNotFoundByIdException: If user does not exist.

        """
        user: User | None = await self._user_dao.delete_by_id(user_id)
        if not user:
            raise UserNotFoundByIdException
        if (
            current_user.id != user_id and current_user.role != UserRole.ADMIN
        ) or (
            current_user.role == UserRole.ADMIN and user.role == UserRole.ADMIN
        ):
            raise UserHasNoPermissionPermission
        await self._session.commit()
        return UserResponseShema.model_validate(user)

    async def get_all_users(
        self,
        *,
        page: int = 1,
        limit: int = 8,
        search: str | None = None,
    ) -> tuple[
        list[UserListItemSchema],
        int,
        int,
        int,
        int,
    ]:
        """Get all users with pagination.

        Args:
            page: Page number (1-based).
            limit: Number of items per page.
            search: Search term for user name, surname, or email.

        Returns:
            tuple containing:
                - List of users.
                - Total count of users.
                - Current page number.
                - Total number of pages.
                - Number of items shown.

        """
        offset = (page - 1) * limit
        total = await self._user_dao.count_all(search=search)
        users = await self._user_dao.get_all(
            offset=offset,
            limit=limit,
            search=search,
        )

        total_pages = (total + limit - 1) // limit if total > 0 else 1
        showing = len(users)

        # Convert to response schema
        items = []
        for user in users:
            full_name = f'{user.name} {user.surname}'
            # Get last_login if field exists, otherwise None
            last_login = getattr(user, 'last_login', None)
            items.append(
                UserListItemSchema(
                    full_name=full_name,
                    email=user.email,
                    role=user.role,
                    is_active=user.is_active,
                    last_login=last_login,
                )
            )

        return (
            items,
            total,
            page,
            total_pages,
            showing,
        )
