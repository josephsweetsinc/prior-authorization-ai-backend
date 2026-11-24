from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from config.settings import Settings
from core import get_service
from dependencies import get_current_user, rate_limiter
from models import User
from schemas import (
    CreateUserRequestSchema,
    PasswordChangeRequestSchema,
    PasswordResetConfirmSchema,
    PasswordResetRequestSchema,
    PasswordResetVerifySchema,
    RefreshTokenRequestSchema,
    TokenSchemas,
    UserResponseShema,
)
from services import UserService
from services.auth import AuthService
from services.password import PasswordService

auth_router = APIRouter()
settings = Settings.load()


@auth_router.post(
    path='/signup',
    description='Create new user.',
    response_model=UserResponseShema,
)
async def signup_user(
    user_data: CreateUserRequestSchema,
    service: Annotated[UserService, Depends(get_service(UserService))],
) -> UserResponseShema:
    """Create a new user in the system.

    Args:
        user_data (CreateUserRequestSchema): Schema with new user data.
        service (UserService): Service for user-related operations.

    Returns:
        UserResponseShema: Schema representing the newly created user.

    """
    return await service.create_new_user(user_data=user_data)


@auth_router.post(
    path='/login',
    response_model=TokenSchemas,
    summary='User login',
    description=(
        'Authenticate user with email and password to get access to tokens.'
    ),
)
async def login_user(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: Annotated[AuthService, Depends(get_service(AuthService))],
    _rate_limit: Annotated[
        None,
        Depends(
            rate_limiter(action='login', limit=10, window_seconds=900)
        ),
    ],
) -> TokenSchemas:
    """Authenticate user and return access and refresh tokens.

    Args:
        form_data (OAuth2PasswordRequestForm): Username and password.
        service (AuthService): Auth service dependency.
        _rate_limit: Per-IP rate limit (max 10 attempts / 15 min),
            to slow down password-guessing scripts.

    Returns:
        TokenSchemas: Access and refresh tokens with type.

    """
    user = await service.auth_user(
        email=form_data.username,
        password=form_data.password,
    )
    token: TokenSchemas = await service.create_token(
        author_id=user.id, user_role=user.role
    )
    return token


@auth_router.post(
    path='/refresh',
    response_model=TokenSchemas,
    summary='Refresh access token',
    description='Get new access and refresh tokens using a valid one.',
)
async def refresh_token(
    refresh_request: Annotated[RefreshTokenRequestSchema, Depends()],
    service: Annotated[AuthService, Depends(get_service(AuthService))],
) -> TokenSchemas:
    """Refresh access and refresh tokens using a valid refresh token.

    Args:
        refresh_request (RefreshTokenRequestSchema): Schema containing
            the refresh token.
        service (AuthService): Auth service dependency.

    Returns:
        TokenSchemas: New access and refresh tokens.

    """
    token: TokenSchemas = await service.refresh_token(
        refresh_token=refresh_request.refresh_token,
    )
    return token


@auth_router.delete(
    path='/logout',
    status_code=204,
    summary='User logout',
    description='Invalidate the provided refresh token to log out the user.',
)
async def logout_user(
    refresh_request: Annotated[RefreshTokenRequestSchema, Depends()],
    service: Annotated[AuthService, Depends(get_service(AuthService))],
) -> None:
    """Invalidate the provided refresh token, logging out the user.

    Args:
        refresh_request (RefreshTokenRequestSchema): Schema containing
            the refresh token to invalidate.
        service (AuthService): Auth service dependency.

    Returns:
        None

    """
    await service.logout_user(refresh_request.refresh_token)


@auth_router.post(
    path='/password-reset/request',
    status_code=204,
    summary='Request password reset',
    description='Request password reset by sending a 5-digit code'
    ' to user email.',
)
async def request_password_reset(
    request_data: PasswordResetRequestSchema,
    service: Annotated[PasswordService, Depends(get_service(PasswordService))],
    _rate_limit: Annotated[
        None,
        Depends(
            rate_limiter(
                action='password-reset-request', limit=5, window_seconds=3600
            )
        ),
    ],
) -> None:
    """Request password reset by sending code to user's email.

    Args:
        request_data (PasswordResetRequestSchema): Schema containing user email.
        service (PasswordService): Password reset service dependency.
        _rate_limit: Per-IP rate limit (max 5 / hour), to stop this
            from being used to spam someone's inbox with reset codes.

    Returns:
        None

    """
    await service.request_password_reset(email=request_data.email)


@auth_router.post(
    path='/password-reset/verify',
    status_code=204,
    summary='Verify password reset code',
    description='Verify the OTP code sent to email before resetting password.',
)
async def verify_password_reset_code(
    request_data: PasswordResetVerifySchema,
    service: Annotated[PasswordService, Depends(get_service(PasswordService))],
    _rate_limit: Annotated[
        None,
        Depends(
            rate_limiter(
                action='password-reset-verify', limit=10, window_seconds=900
            )
        ),
    ],
) -> None:
    """Verify password reset code.

    Args:
        request_data (PasswordResetVerifySchema): Schema containing code.
        service (PasswordService): Password reset service dependency.
        _rate_limit: Per-IP rate limit (max 10 attempts / 15 min).
            The code itself is only 5 digits (100,000 combinations),
            so without this, brute-forcing it within its 15-minute
            expiration window would otherwise be realistic.

    Returns:
        None

    """
    await service.verify_code(code=request_data.code)


@auth_router.post(
    path='/password-reset/confirm',
    status_code=204,
    summary='Confirm password reset',
    description='Reset password using verified code. '
    'Code must be verified first and not older than 5 minutes.',
)
async def confirm_password_reset(
    request_data: PasswordResetConfirmSchema,
    service: Annotated[PasswordService, Depends(get_service(PasswordService))],
) -> None:
    """Reset password using verified code.

    Args:
        request_data (PasswordResetConfirmSchema): Schema containing email
            and new password. Code must be verified first via /verify
            and not older than 5 minutes.
        service (PasswordService): Password reset service dependency.

    Returns:
        None

    """
    await service.reset_password(
        email=request_data.email,
        new_password=request_data.new_password,
    )


@auth_router.post(
    path='/password-change',
    status_code=204,
    summary='Change password',
    description='Change password using current password.',
)
async def change_password(
    user: Annotated[User, Depends(get_current_user)],
    request_data: PasswordChangeRequestSchema,
    service: Annotated[PasswordService, Depends(get_service(PasswordService))],
) -> None:
    """Change password.

    Args:
        user: (User): Current authenticated user.
        request_data (PasswordResetConfirmSchema): Schema containing code
            and new password.
        service (PasswordService): Password reset service dependency.

    Returns:
        None

    """
    await service.change_password(
        user=user,
        old_password=request_data.old_password,
        new_password=request_data.new_password,
    )
