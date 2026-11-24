from fastapi import HTTPException


class AuthorizationException(HTTPException):
    """Base exception for all authentication-related errors."""


class WrongCredentialsException(AuthorizationException):
    """Exception raised when provided credentials are invalid.

    Attributes:
        status_code (int): HTTP status code for exception (401 Unauthorized).
        detail (str): Human-readable explanation of the error.

    """

    def __init__(self) -> None:
        """Initialize WrongCredentialsException with a default message."""
        super().__init__(
            status_code=401,
            detail='Invalid credentials provided',
        )


class AccessTokenExpiredException(AuthorizationException):
    """Exception raised when an access token has expired.

    Attributes:
        status_code (int): HTTP status code for exception (401 Unauthorized).
        detail (str): Human-readable explanation indicating token expiry.

    """

    def __init__(self) -> None:
        """Initialize AccessTokenExpiredException with default message."""
        super().__init__(
            status_code=401,
            detail='Access token has expired',
        )


class RefreshTokenException(AuthorizationException):
    """Exception raised when a refresh token is invalid, expired.

    Attributes:
        status_code (int): HTTP status code for the exception (403 Forbidden).
        detail (str): Human-readable explanation of the failure.

    """

    def __init__(self) -> None:
        """Initialize RefreshTokenException with default message."""
        super().__init__(
            status_code=403,
            detail=(
                'Cannot process refresh token. It may be expired, invalid, '
                'or attached to a deleted user.'
            ),
        )


class NoUpdateDataException(AuthorizationException):
    """Raised when no update data is provided."""

    def __init__(self) -> None:
        """Initialize the exception with a predefined error message."""
        super().__init__(
            status_code=400,
            detail='No update data provided',
        )


class NoFiltersException(AuthorizationException):
    """Raised when no filters are provided for an operation."""

    def __init__(self) -> None:
        """Initialize the exception with a predefined error message."""
        super().__init__(
            status_code=400,
            detail='No filters provided for operation',
        )


class RateLimitExceededException(AuthorizationException):
    """Raised when a client exceeds a per-IP rate limit.

    Attributes:
        status_code (int): HTTP status code for exception (429).
        detail (str): Human-readable explanation of the error.

    """

    def __init__(self) -> None:
        """Initialize RateLimitExceededException with a default message."""
        super().__init__(
            status_code=429,
            detail='Too many attempts. Please try again later.',
        )
