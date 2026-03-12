from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from core import (
    EmailMixinSchema,
    NameMixinSchema,
    PasswordMixinSchema,
    SurnameMixinSchema,
)
from models.user import UserRole
from schemas import OrganizationResponseSchema

# E.164: 10–15 digits; optional leading + and spaces/dashes/parentheses
PHONE_DIGITS_RE = re.compile(r'[\d]')
PHONE_MIN_DIGITS = 10
PHONE_MAX_DIGITS = 15


def _normalize_phone(value: str | None) -> str | None:
    """Normalize phone to digits only; validate length; raise friendly error."""
    if value is None:
        return None
    digits = ''.join(PHONE_DIGITS_RE.findall(value))
    if len(digits) < PHONE_MIN_DIGITS or len(digits) > PHONE_MAX_DIGITS:
        raise ValueError('Invalid phone number format')
    return digits


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
            min_length=1,
            max_length=32,
            description='Phone number (digits; +, spaces, dashes allowed)',
            examples=['+1 234 567 8901', '12345678900'],
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

    @field_validator('phone_number', mode='before')
    @classmethod
    def normalize_phone_number(cls, value: str | None) -> str | None:
        return _normalize_phone(value)


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
            examples=['John'],
        ),
    ]
    surname: Annotated[
        str | None,
        Field(
            None,
            min_length=3,
            max_length=15,
            examples=['Doe'],
        ),
    ]
    email: Annotated[
        EmailStr | None,
        Field(
            None,
            min_length=3,
            max_length=254,
            pattern=r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$',
            examples=['admin@admin.com'],
        ),
    ]

    @model_validator(mode='after')
    def validate_at_least_one_field(self) -> UpdateUserRequestSchema:
        """Validate that at least one field is provided for update."""
        if self.name is None and self.surname is None and self.email is None:
            raise ValueError(  # noqa: TRY003
                'At least one field (name, surname, or email) must be provided'
            )
        return self


class UpdateMeRequestSchema(BaseModel):
    """Update the current user profile request schema."""

    name: Annotated[
        str | None,
        Field(
            None,
            min_length=3,
            max_length=15,
            examples=['John'],
            description='First name of the user',
        ),
    ]
    surname: Annotated[
        str | None,
        Field(
            None,
            min_length=3,
            max_length=15,
            examples=['Doe'],
            description='Last name of the user',
        ),
    ]
    email: Annotated[
        EmailStr | None,
        Field(
            None,
            min_length=3,
            max_length=254,
            pattern=r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$',
            examples=['user@example.com'],
            description='Email of the user',
        ),
    ]
    phone: Annotated[
        str | None,
        Field(
            None,
            min_length=1,
            max_length=32,
            description='Phone number (digits; +, spaces, dashes allowed)',
            examples=['+1 234 567 8901', '12345678900'],
        ),
    ]
    position: Annotated[
        str | None,
        Field(
            None,
            min_length=3,
            max_length=64,
            examples=['Doctor'],
            description='User position',
        ),
    ]
    place_of_work: Annotated[
        str | None,
        Field(
            None,
            min_length=3,
            max_length=64,
            examples=['Hospital'],
            description='Place of work',
        ),
    ]

    @field_validator('phone', mode='before')
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        return _normalize_phone(value)

    @model_validator(mode='after')
    def validate_at_least_one_field(self) -> UpdateMeRequestSchema:
        """Validate that at least one field is provided for update."""
        if (
            self.name is None
            and self.surname is None
            and self.email is None
            and self.phone is None
            and self.position is None
            and self.place_of_work is None
        ):
            raise ValueError(  # noqa: TRY003
                'At least one field (name, surname, email, phone, position, or '
                'place_of_work) must be'
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
    phone: Annotated[
        str | None,
        Field(
            default=None,
            alias='phone_number',
            description='Phone number of the user',
        ),
    ] = None
    position: Annotated[
        str | None,
        Field(
            default=None,
            description='Position of the user',
        ),
    ] = None
    place_of_work: Annotated[
        str | None,
        Field(
            default=None,
            description='Place of work of the user',
        ),
    ] = None
    last_login: Annotated[
        datetime | None,
        Field(
            default=None,
            description='Date and time of last login',
        ),
    ] = None
    created_at: Annotated[
        datetime,
        Field(
            description='Date and time when the account was created',
        ),
    ]
    avatar_url: Annotated[
        str | None,
        Field(
            default=None,
            description='Presigned URL for user avatar image',
        ),
    ] = None
    organization: Annotated[
        OrganizationResponseSchema | None,
        Field(
            default=None,
            description='Organization information attached to the user',
        ),
    ] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UserListItemSchema(BaseModel):
    """Schema for user list item."""

    id: Annotated[
        int, Field(description='Unique identifier of the user', examples=[1])
    ]
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
    last_approved_at: Annotated[
        datetime | None,
        Field(
            None,
            description='Date and time when the user was last approved',
            examples=[datetime(2025, 1, 1, 12, 0, 0, tzinfo=None)],  # noqa: DTZ001
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
