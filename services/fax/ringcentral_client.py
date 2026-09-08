"""Thin client for the RingCentral fax REST API.

Only the pieces needed for inbound fax intake are implemented so far:
fetching a message's metadata and downloading its document attachment.
Outbound sending will be added in a later slice.

Field names for message-store responses are based on RingCentral's
published API documentation; they should be verified against a live
sandbox response the first time this runs against a real account, since
RingCentral does not publish a formal JSON schema for this endpoint.
"""

import logging
import time
from typing import Any

import httpx

from config.settings import Settings
from exceptions import FaxProviderException

logger = logging.getLogger(__name__)

TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 60


class RingCentralClient:
    """Client for RingCentral's fax-related REST API endpoints."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize RingCentralClient.

        Args:
            settings: Application settings. If None, loads from Settings.
            http_client: Optional httpx.AsyncClient to use (for testing).

        """
        self._settings = (settings or Settings.load()).ringcentral_settings
        self._http_client = http_client or httpx.AsyncClient(
            base_url=self._settings.SERVER_URL,
            timeout=30.0,
        )
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    async def _get_access_token(self) -> str:
        """Get a valid access token, refreshing it if expired.

        Uses RingCentral's JWT bearer grant, intended for server-to-server
        authentication with no interactive login.

        Returns:
            str: Valid bearer access token.

        Raises:
            FaxProviderException: If the token request fails.

        """
        now = time.monotonic()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        try:
            response = await self._http_client.post(
                '/restapi/oauth/token',
                auth=(
                    self._settings.CLIENT_ID,
                    self._settings.CLIENT_SECRET,
                ),
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                data={
                    'grant_type': (
                        'urn:ietf:params:oauth:grant-type:jwt-bearer'
                    ),
                    'assertion': self._settings.JWT,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception('RingCentral token request failed')
            raise FaxProviderException(  # noqa: TRY003
                f'Failed to authenticate with RingCentral: {exc}'
            ) from exc

        payload = response.json()
        self._access_token = payload['access_token']
        expires_in = payload.get('expires_in', 3600)
        self._token_expires_at = (
            now + expires_in - TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS
        )
        return self._access_token

    async def _authenticated_get(self, url: str) -> httpx.Response:
        """Make an authenticated GET request to the RingCentral API.

        Args:
            url: Path or full URL to request.

        Returns:
            httpx.Response: The response object.

        Raises:
            FaxProviderException: If the request fails.

        """
        token = await self._get_access_token()
        try:
            response = await self._http_client.get(
                url,
                headers={'Authorization': f'Bearer {token}'},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception('RingCentral API request failed: %s', url)
            raise FaxProviderException(  # noqa: TRY003
                f'RingCentral API request failed: {exc}'
            ) from exc
        return response

    async def get_message(self, message_id: str) -> dict[str, Any]:
        """Get message-store metadata for a fax message.

        Args:
            message_id: RingCentral message ID.

        Returns:
            dict: Message metadata, including its list of attachments.

        """
        response = await self._authenticated_get(
            '/restapi/v1.0/account/~/extension/~/message-store/'
            f'{message_id}',
        )
        result: dict[str, Any] = response.json()
        return result

    @staticmethod
    def get_document_attachment(
        message: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Pick the fax document attachment out of a message's attachments.

        A fax message typically has one attachment that is the actual
        document (PDF or TIFF) and may have other, non-document
        attachments (e.g. a text summary). Prefers PDF, then any image,
        falling back to the first attachment if content types are
        unrecognized.

        Args:
            message: Message metadata as returned by get_message().

        Returns:
            dict | None: The chosen attachment's metadata, or None if the
                message has no attachments.

        """
        attachments: list[dict[str, Any]] = message.get('attachments', [])
        if not attachments:
            return None

        for attachment in attachments:
            content_type = attachment.get('contentType', '')
            if content_type == 'application/pdf':
                return attachment
        for attachment in attachments:
            content_type = attachment.get('contentType', '')
            if content_type.startswith('image/'):
                return attachment
        return attachments[0]

    async def download_attachment(
        self,
        *,
        message_id: str,
        attachment_id: str,
    ) -> tuple[bytes, str]:
        """Download a message attachment's raw content.

        Args:
            message_id: RingCentral message ID.
            attachment_id: ID of the attachment to download.

        Returns:
            Tuple of (content bytes, content type).

        """
        response = await self._authenticated_get(
            '/restapi/v1.0/account/~/extension/~/message-store/'
            f'{message_id}/content/{attachment_id}',
        )
        content_type = response.headers.get(
            'content-type', 'application/octet-stream'
        )
        return response.content, content_type

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http_client.aclose()
