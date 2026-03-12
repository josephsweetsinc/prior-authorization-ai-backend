import logging
from datetime import UTC, datetime, timedelta
from io import BytesIO

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core import BaseService
from core.constants import MAX_AVATAR_SIZE
from dao import OrganizationDAO, UserDAO
from exceptions import (
    EmailAlreadyRegisteredException,
    IncorrectFileSizeException,
    UnknownFiletypeException,
    UserHasNoPermissionPermission,
    UserNotFoundByIdException, UserDeactivatedException,
)
from models import User
from models.user import UserRole
from schemas import (
    CreateUserByAdminRequestSchema,
    CreateUserRequestSchema,
    OrganizationResponseSchema,
    UpdateMeRequestSchema,
    UpdateUserRequestSchema,
    UserListItemSchema,
    UserResponseShema,
)
from services.aws.actions import S3Actions, generate_storage_key
from services.jwt.hasher import Hasher

logger = logging.getLogger(__name__)


class UserService(BaseService):
    """Service layer for managing user-related operations."""

    def __init__(
        self,
        db_session: AsyncSession,
        *,
        user_dao: UserDAO | None = None,
        hash_service: Hasher | None = None,
        s3_actions: S3Actions | None = None,
    ):
        """Initialize UserService.

        Args:
            db_session (AsyncSession): Database session.
            user_dao (UserDAO | None): Optional UserDAO instance.
            hash_service (Hasher | None): Optional password hasher.
            s3_actions (S3Actions | None): Optional S3 actions instance.

        """
        super().__init__(db_session)
        self._user_dao = user_dao or UserDAO(db_session)
        self._hash_service = hash_service or Hasher()
        self._s3_actions = s3_actions or S3Actions()

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

        # Load organization if exists
        organization_dao = OrganizationDAO(self._session)
        organization = await organization_dao.get_by_user_id(created_user.id)

        # Build response data to avoid lazy loading issues
        response_data = {
            'id': created_user.id,
            'name': created_user.name,
            'surname': created_user.surname,
            'email': created_user.email,
            'role': created_user.role,
            'is_active': created_user.is_active,
            'phone': created_user.phone_number,
            'position': created_user.position,
            'place_of_work': created_user.place_of_work,
            'last_login': created_user.last_login,
            'created_at': created_user.created_at,
            'avatar_url': None,
            'organization': (
                OrganizationResponseSchema.model_validate(organization)
                if organization
                else None
            ),
        }

        return UserResponseShema.model_validate(response_data)

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
            raise UserDeactivatedException
        return user

    async def get_me(self, user_id: int) -> UserResponseShema:
        """Get current user profile with organization and avatar URL.

        Args:
            user_id: User ID.

        Returns:
            UserResponseShema: User information with organization.

        Raises:
            UserNotFoundByIdException: If user not found.

        """
        user = await self.get_user_by_id(user_id)

        # Load organization if exists
        organization_dao = OrganizationDAO(self._session)
        organization = await organization_dao.get_by_user_id(user_id)

        # Generate presigned URL for avatar if exists
        avatar_url = None
        if user.avatar_key:
            try:
                avatar_url = self._s3_actions.get_presigned_url(
                    key=user.avatar_key,
                    expires_in=self._s3_actions.S3_EXPIRATION_TIME,
                    require_object=True,
                )
            except Exception:
                # If avatar doesn't exist in S3, set to None
                avatar_url = None

        # Build response data
        response_data = {
            'id': user.id,
            'name': user.name,
            'surname': user.surname,
            'email': user.email,
            'role': user.role,
            'is_active': user.is_active,
            'phone': user.phone_number,
            'position': user.position,
            'place_of_work': user.place_of_work,
            'last_login': user.last_login,
            'created_at': user.created_at,
            'avatar_url': avatar_url,
            'organization': (
                OrganizationResponseSchema.model_validate(organization)
                if organization
                else None
            ),
        }

        return UserResponseShema.model_validate(response_data)

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
        try:
            user: User | None = await self._user_dao.update_by_id(
                user_id,
                name=user_data.name,
                surname=user_data.surname,
                email=user_data.email,
            )
        except IntegrityError:
            raise EmailAlreadyRegisteredException from None
        await self._session.commit()
        if not user:
            raise UserNotFoundByIdException

        # Load organization if exists
        organization_dao = OrganizationDAO(self._session)
        organization = await organization_dao.get_by_user_id(user_id)

        # Build response data to avoid lazy loading issues
        response_data = {
            'id': user.id,
            'name': user.name,
            'surname': user.surname,
            'email': user.email,
            'role': user.role,
            'is_active': user.is_active,
            'phone': user.phone_number,
            'position': user.position,
            'place_of_work': user.place_of_work,
            'last_login': user.last_login,
            'created_at': user.created_at,
            'avatar_url': None,
            'organization': (
                OrganizationResponseSchema.model_validate(organization)
                if organization
                else None
            ),
        }

        return UserResponseShema.model_validate(response_data)

    async def update_me_profile(
        self,
        user_id: int,
        user_data: UpdateMeRequestSchema,
    ) -> UserResponseShema:
        """Update current user profile fields (phone, position, place_of_work).

        Args:
            user_id: User ID.
            user_data: UpdateMeRequestSchema with fields to update.

        Returns:
            UserResponseShema: Updated user information.

        Raises:
            UserNotFoundByIdException: If user not found.

        """
        user: User | None = await self._user_dao.update_profile_fields_by_id(
            user_id,
            name=user_data.name,
            surname=user_data.surname,
            email=user_data.email,
            phone_number=user_data.phone,
            position=user_data.position,
            place_of_work=user_data.place_of_work,
        )
        await self._session.commit()
        if not user:
            raise UserNotFoundByIdException

        # Load organization if exists
        organization_dao = OrganizationDAO(self._session)
        organization = await organization_dao.get_by_user_id(user_id)

        # Generate presigned URL for avatar if exists
        avatar_url = None
        if user.avatar_key:
            try:
                avatar_url = self._s3_actions.get_presigned_url(
                    key=user.avatar_key,
                    expires_in=self._s3_actions.S3_EXPIRATION_TIME,
                    require_object=True,
                )
            except Exception:
                # If avatar doesn't exist in S3, set to None
                avatar_url = None

        # Build response
        response_data = {
            'id': user.id,
            'name': user.name,
            'surname': user.surname,
            'email': user.email,
            'role': user.role,
            'is_active': user.is_active,
            'phone': user.phone_number,
            'position': user.position,
            'place_of_work': user.place_of_work,
            'last_login': user.last_login,
            'created_at': user.created_at,
            'avatar_url': avatar_url,
            'organization': (
                OrganizationResponseSchema.model_validate(organization)
                if organization
                else None
            ),
        }

        return UserResponseShema.model_validate(response_data)

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

        # Load organization if exists
        organization_dao = OrganizationDAO(self._session)
        organization = await organization_dao.get_by_user_id(user_id)

        # Build response data to avoid lazy loading issues
        response_data = {
            'id': user.id,
            'name': user.name,
            'surname': user.surname,
            'email': user.email,
            'role': user.role,
            'is_active': user.is_active,
            'phone': user.phone_number,
            'position': user.position,
            'place_of_work': user.place_of_work,
            'last_login': user.last_login,
            'created_at': user.created_at,
            'avatar_url': None,
            'organization': (
                OrganizationResponseSchema.model_validate(organization)
                if organization
                else None
            ),
        }

        return UserResponseShema.model_validate(response_data)

    async def get_all_users(
        self,
        *,
        page: int = 1,
        limit: int = 8,
        search: str | None = None,
        roles: list[UserRole] | None = None,
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
            roles: List of user roles to filter by.

        Returns:
            tuple containing:
                - List of users.
                - Total count of users.
                - Current page number.
                - Total number of pages.
                - Number of items shown.

        """
        offset = (page - 1) * limit
        total = await self._user_dao.count_all(search=search, roles=roles)
        users = await self._user_dao.get_all(
            offset=offset,
            limit=limit,
            search=search,
            roles=roles,
        )

        total_pages = (total + limit - 1) // limit if total > 0 else 1
        showing = len(users)

        # Convert to response schema
        items = [
            UserListItemSchema(
                id=user.id,
                full_name=f'{user.name} {user.surname}',
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                last_approved_at=user.last_approved_at,
            )
            for user in users
        ]

        return (
            items,
            total,
            page,
            total_pages,
            showing,
        )

    async def upload_avatar(
        self,
        user_id: int,
        file: UploadFile,
    ) -> UserResponseShema:
        """Upload user avatar image.

        Args:
            user_id: User ID.
            file: Uploaded avatar file (JPEG or PNG, max 5MB).

        Returns:
            UserResponseShema: Updated user information.

        Raises:
            UserNotFoundByIdException: If user not found.
            UnknownFiletypeException: If file type is not JPEG or PNG.
            IncorrectFileSizeException: If file size exceeds 5MB.

        """
        # Validate file type
        allowed_mime_types = {'image/jpeg', 'image/png'}
        content_type = file.content_type

        if not content_type or content_type not in allowed_mime_types:
            raise UnknownFiletypeException(allowed_types=['JPEG', 'PNG'])

        # Read file content
        content = await file.read()
        file_size = len(content)

        # Validate file size (5MB max)
        if file_size > MAX_AVATAR_SIZE:
            raise IncorrectFileSizeException(max_size_mb=5)

        if file_size == 0:
            raise IncorrectFileSizeException(max_size_mb=5)

        # Get user to check if exists and get old avatar key
        user = await self.get_user_by_id(user_id)
        old_avatar_key = user.avatar_key

        # Convert bytes to BytesIO for S3Actions
        file_obj = BytesIO(content)

        # Generate S3 key for avatar

        file_extension = '.jpg' if content_type == 'image/jpeg' else '.png'
        s3_key = generate_storage_key(
            prefix=f'users/{user_id}/avatars',
            file_extension=file_extension,
        )

        # Upload to S3 directly (we already validated the file)
        file_obj.seek(0)
        self._s3_actions.upload_to_s3(
            key=s3_key,
            file_obj=file_obj,
            content_type=content_type,
        )

        # Update user avatar key
        updated_user = await self._user_dao.update_avatar_key(
            user_id=user_id,
            avatar_key=s3_key,
        )

        if not updated_user:
            raise UserNotFoundByIdException

        # Delete old avatar from S3 if exists
        if old_avatar_key:
            try:
                self._s3_actions.s3_client.delete_object(
                    Bucket=self._s3_actions.aws_bucket_name,
                    Key=old_avatar_key,
                )
            except Exception:
                # Log error but don't fail the request
                logger.exception('Failed to delete old avatar')

        await self._session.commit()

        # Generate presigned URL for avatar
        avatar_url = None
        if updated_user.avatar_key:
            avatar_url = self._s3_actions.get_presigned_url(
                key=updated_user.avatar_key,
                expires_in=self._s3_actions.S3_EXPIRATION_TIME,
                require_object=True,
            )

        # Load organization if exists
        organization_dao = OrganizationDAO(self._session)
        organization = await organization_dao.get_by_user_id(user_id)

        # Build response with avatar URL
        response_data = {
            'id': updated_user.id,
            'name': updated_user.name,
            'surname': updated_user.surname,
            'email': updated_user.email,
            'role': updated_user.role,
            'is_active': updated_user.is_active,
            'phone': updated_user.phone_number,
            'position': updated_user.position,
            'place_of_work': updated_user.place_of_work,
            'last_login': updated_user.last_login,
            'created_at': updated_user.created_at,
            'avatar_url': avatar_url,
            'organization': (
                OrganizationResponseSchema.model_validate(organization)
                if organization
                else None
            ),
        }

        return UserResponseShema.model_validate(response_data)

    async def deactivate_unapproved_providers(self) -> int:
        """Deactivate providers whose last_approved_at is older than 30 days.

        Returns:
            int: Number of deactivated users.
        """
        cutoff_date = datetime.now(UTC) - timedelta(days=30)
        deactivated_count = (
            await self._user_dao.deactivate_unapproved_providers(
                cutoff_date=cutoff_date
            )
        )
        if deactivated_count > 0:
            await self._session.commit()
        return deactivated_count

    async def activate_user_by_id(self, user_id: int) -> UserResponseShema:
        """Activate a user by ID (admin only).

        Sets ``is_active = True``, clears ``deleted_at`` and resets
        ``last_approved_at`` to now so the 30-day approval window restarts.

        Args:
            user_id: ID of the user to activate.

        Returns:
            UserResponseShema: The activated user information.

        Raises:
            UserNotFoundByIdException: If no user exists with the given ID.

        """
        from sqlalchemy import update as sa_update  # noqa: PLC0415

        # Activate + reset approval timestamp in one round-trip
        stmt = (
            sa_update(User)
            .where(User.id == user_id)
            .values(
                is_active=True,
                deleted_at=None,
                last_approved_at=datetime.now(UTC),
            )
            .returning(User)
        )
        result = await self._session.execute(stmt)
        user: User | None = result.scalar_one_or_none()
        if not user:
            raise UserNotFoundByIdException

        await self._session.commit()

        # Load organization if exists
        organization_dao = OrganizationDAO(self._session)
        organization = await organization_dao.get_by_user_id(user_id)

        response_data = {
            'id': user.id,
            'name': user.name,
            'surname': user.surname,
            'email': user.email,
            'role': user.role,
            'is_active': user.is_active,
            'phone': user.phone_number,
            'position': user.position,
            'place_of_work': user.place_of_work,
            'last_login': user.last_login,
            'created_at': user.created_at,
            'avatar_url': None,
            'organization': (
                OrganizationResponseSchema.model_validate(organization)
                if organization
                else None
            ),
        }

        return UserResponseShema.model_validate(response_data)


