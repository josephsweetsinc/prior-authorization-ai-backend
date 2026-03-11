from fastapi import HTTPException


class UserException(HTTPException):
    """Base exception for all user-related errors."""


class BadPasswordSchemaException(UserException):
    """Raised when password schema is invalid."""

    def __init__(self) -> None:
        """Initialize BadPasswordSchemaException with a default message."""
        super().__init__(
            status_code=422,
            detail=(
                'Password should contain at least one uppercase letter, '
                'one lowercase letter, one digit, and one special '
                'character @$!%*?&.'
            ),
        )


class EmailAlreadyRegisteredException(UserException):
    """Raised when email already registered."""

    def __init__(self) -> None:
        """Initialize EmailAlreadyRegisteredException with a default message."""
        super().__init__(
            status_code=409,
            detail=(
                'You are trying to create user with email'
                ' that already has been taken'
            ),
        )


class UserNotFoundByIdException(UserException):
    """Raised when user with provided id is not found."""

    def __init__(self) -> None:
        """Initialize UserNotFoundByIdException with a default message."""
        super().__init__(
            status_code=404,
            detail='User by this id not found.',
        )


class UserIsNotActiveException(UserException):
    """Raised when user is not active."""

    def __init__(self) -> None:
        """Initialize UserIsNotActiveException with a default message."""
        super().__init__(
            status_code=404,
            detail='User is not active.',
        )

class UserDeactivatedException(UserException):
    """Raised when user is not active."""

    def __init__(self) -> None:
        """Initialize UserIsNotActiveException with a default message."""
        super().__init__(
            status_code=402,
            detail='User is not active contact admin.',
        )


class UserHasNoPermissionPermission(UserException):
    """Raised when user does not have permission."""

    def __init__(self) -> None:
        """Initialize UserHasNoPermissionPermission with a default message."""
        super().__init__(
            status_code=404,
            detail='Current authenticated user'
            ' has no right to access this data',
        )
