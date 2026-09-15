from fastapi import HTTPException


class FaxException(HTTPException):
    """Exception raised when a fax operation fails."""


class FaxNotFoundException(FaxException):
    """Exception raised when a fax is not found."""

    def __init__(self) -> None:
        """Initialize FaxNotFoundException."""
        super().__init__(
            status_code=404,
            detail='Fax was not found by given id.',
        )


class FaxWebhookUnauthorizedException(FaxException):
    """Exception raised when a fax webhook request fails authentication."""

    def __init__(self) -> None:
        """Initialize FaxWebhookUnauthorizedException."""
        super().__init__(
            status_code=401,
            detail='Fax webhook request failed authentication.',
        )


class FaxProviderException(FaxException):
    """Exception raised when the fax provider API returns an error."""

    def __init__(self, detail: str) -> None:
        """Initialize FaxProviderException.

        Args:
            detail: Description of the provider error.

        """
        super().__init__(
            status_code=502,
            detail=f'Fax provider error: {detail}',
        )
