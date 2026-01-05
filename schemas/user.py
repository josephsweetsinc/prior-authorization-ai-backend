from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from core import (
    EmailMixinSchema,
    NameMixinSchema,
    PasswordMixinSchema,
    SurnameMixinSchema,
)
from models.user import UserRole


class _BaseUserRequestSchema(
    NameMixinSchema, SurnameMixinSchema, EmailMixinSchema, PasswordMixinSchema
):
    """Base schema for user-related requests.

    This schema combines common user fields and validation rules
    using mixins. It is intended to be used as a parent class
    for more specific user request schemas (e.g., registration,
    password reset, admin user creation).

    Notes
    -----
    - This is an internal base schema. Do not use it directly in API responses.
    - It provides unified validation rules via mixins, preventing duplication.

    """


class CreateUserRequestSchema(_BaseUserRequestSchema):
    """User creation request schema."""

    phone_number: Annotated[
        str,
        Field(
            min_length=10,
            max_length=15,
            pattern=r'^1\d{10}$',
            examples=['12345678900'],
        ),
    ]
    position: Annotated[
        str,
        Field(min_length=3, max_length=64, examples=['Doctor']),
    ]
    place_of_work: Annotated[
        str,
        Field(min_length=3, max_length=64, examples=['Hospital']),
    ]


class CreateUserByAdminRequestSchema(_BaseUserRequestSchema):
    """Create user with role."""

    role: UserRole


class UpdateUserRequestSchema(BaseModel):
    """User update request schema."""

    name: Annotated[
        str | None,
        Field(
            None,
            min_length=3,
            max_length=15,
            pattern=r'^[a-zA-Z]+$',
            examples=['John'],
        ),
    ]
    surname: Annotated[
        str | None,
        Field(
            None,
            min_length=3,
            max_length=15,
            pattern=r'^[a-zA-Z]+$',
            examples=['Doe'],
        ),
    ]
    email: Annotated[
        EmailStr | None,
        Field(
            None,
            min_length=3,
            max_length=30,
            pattern=r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$',
            examples=['admin@admin.com'],
        ),
    ]

    @model_validator(mode='after')
    def validate_at_least_one_field(self) -> 'UpdateUserRequestSchema':
        """Validate that at least one field is provided for update."""
        if self.name is None and self.surname is None and self.email is None:
            raise ValueError(  # noqa: TRY003
                'At least one field (name, surname, or email) must be provided'
            )
        return self


class UserResponseShema(BaseModel):
    """User response schema."""

    id: int
    name: str
    surname: str
    email: str
    role: UserRole
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class UserListItemSchema(BaseModel):
    """Schema for user list item."""

    full_name: Annotated[
        str,
        Field(description='Full name of the user', examples=['John Doe']),
    ]
    email: Annotated[
        EmailStr,
        Field(description='User email address', examples=['john@example.com']),
    ]
    role: Annotated[
        UserRole,
        Field(description='User role', examples=[UserRole.PROVIDER]),
    ]
    is_active: Annotated[
        bool,
        Field(description='Whether the user is active', examples=[True]),
    ]
    last_login: Annotated[
        datetime | None,
        Field(
            None,
            description='Date and time of last login',
            examples=[datetime(2025, 1, 1, 12, 0, 0)],  # noqa: DTZ001
        ),
    ]

    model_config = ConfigDict(from_attributes=True)


class UsersListResponseSchema(BaseModel):
    """Response schema for paginated list of users.

    Attributes:
        items: List of users.
        page: Current page number.
        total: Total number of users.
        showing: Number of items shown on current page.
        total_pages: Total number of pages.

    """

    items: list[UserListItemSchema] = Field(
        description='List of users',
    )
    page: int = Field(
        description='Current page number',
        examples=[1],
    )
    total: int = Field(
        description='Total number of users',
        examples=[50],
    )
    showing: int = Field(
        description='Number of items shown on current page',
        examples=[8],
    )
    total_pages: int = Field(
        description='Total number of pages',
        examples=[7],
    )
