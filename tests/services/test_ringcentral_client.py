"""Tests for RingCentralClient."""

import httpx
import pytest

from exceptions import FaxProviderException
from services.fax.ringcentral_client import RingCentralClient


def _make_client(handler) -> RingCentralClient:
    """Build a RingCentralClient backed by a mock httpx transport."""
    http_client = httpx.AsyncClient(
        base_url='https://fake.ringcentral.test',
        transport=httpx.MockTransport(handler),
    )
    return RingCentralClient(http_client=http_client)


def _token_response(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={'access_token': 'fake-token', 'expires_in': 3600}
    )


class TestSendFax:
    """Test suite for RingCentralClient.send_fax()."""

    @pytest.mark.asyncio
    async def test_send_fax_success_builds_multipart_request(self):
        """Test that send_fax posts the expected multipart parts."""
        captured: dict[str, httpx.Request] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == '/restapi/oauth/token':
                return _token_response(request)
            captured['fax_request'] = request
            return httpx.Response(
                200,
                json={'id': 'msg-out-1', 'messageStatus': 'Queued'},
            )

        client = _make_client(handler)

        result = await client.send_fax(
            to_number='+15559990000',
            attachments=[('doc.pdf', b'%PDF-fake', 'application/pdf')],
            cover_page_text='Cover text',
        )

        assert result == {'id': 'msg-out-1', 'messageStatus': 'Queued'}
        fax_request = captured['fax_request']
        assert fax_request.method == 'POST'
        assert fax_request.url.path == (
            '/restapi/v1.0/account/~/extension/~/fax'
        )
        assert fax_request.headers['Authorization'] == 'Bearer fake-token'
        body = fax_request.content.decode('utf-8', errors='ignore')
        assert 'doc.pdf' in body
        assert 'Cover text' in body
        assert '"phoneNumber": "+15559990000"' in body

        await client.aclose()

    @pytest.mark.asyncio
    async def test_send_fax_without_cover_page_omits_part(self):
        """Test that omitting cover_page_text omits that multipart part."""
        captured: dict[str, httpx.Request] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == '/restapi/oauth/token':
                return _token_response(request)
            captured['fax_request'] = request
            return httpx.Response(
                200, json={'id': 'msg-out-2', 'messageStatus': 'Queued'}
            )

        client = _make_client(handler)

        await client.send_fax(
            to_number='+15559990000',
            attachments=[('doc.pdf', b'%PDF-fake', 'application/pdf')],
        )

        body = captured['fax_request'].content.decode(
            'utf-8', errors='ignore'
        )
        assert 'coverPageText' not in body

        await client.aclose()

    @pytest.mark.asyncio
    async def test_send_fax_raises_on_http_error(self):
        """Test that a failed send raises FaxProviderException."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == '/restapi/oauth/token':
                return _token_response(request)
            return httpx.Response(500, json={'error': 'boom'})

        client = _make_client(handler)

        with pytest.raises(FaxProviderException):
            await client.send_fax(
                to_number='+15559990000',
                attachments=[('doc.pdf', b'%PDF-fake', 'application/pdf')],
            )

        await client.aclose()
