"""Tests for the per-IP rate-limiting dependency."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis
from fastapi import Request

from dependencies.rate_limit import _client_ip, rate_limiter
from exceptions import RateLimitExceededException


def _make_request(headers: dict[str, str] | None = None) -> Request:
    """Build a minimal FastAPI Request for testing header lookups."""
    raw_headers = [
        (key.lower().encode(), value.encode())
        for key, value in (headers or {}).items()
    ]
    scope = {
        'type': 'http',
        'headers': raw_headers,
        'client': ('203.0.113.5', 12345),
    }
    return Request(scope)


class TestClientIp:
    """Test suite for _client_ip()."""

    def test_prefers_x_real_ip(self):
        """Test that X-Real-IP (set by nginx) is used when present."""
        request = _make_request({'X-Real-IP': '198.51.100.9'})
        assert _client_ip(request) == '198.51.100.9'

    def test_falls_back_to_x_forwarded_for(self):
        """Test that X-Forwarded-For is used when X-Real-IP is absent,
        taking only the first (client) address in the chain.
        """  # noqa: D205
        request = _make_request(
            {'X-Forwarded-For': '198.51.100.9, 10.0.0.1'}
        )
        assert _client_ip(request) == '198.51.100.9'

    def test_falls_back_to_request_client(self):
        """Test that request.client.host is used with no proxy headers.

        This is the uvicorn-visible address - behind nginx in
        production that would be nginx itself, which is exactly why
        the proxy headers are checked first.
        """
        request = _make_request()
        assert _client_ip(request) == '203.0.113.5'


class TestRateLimiter:
    """Test suite for rate_limiter()."""

    @pytest.mark.asyncio
    async def test_allows_requests_under_the_limit(self):
        """Test that requests under the limit pass through."""
        mock_client = MagicMock()
        mock_client.incr = AsyncMock(return_value=1)
        mock_client.expire = AsyncMock()

        with patch(
            'dependencies.rate_limit._get_redis_client',
            return_value=mock_client,
        ):
            check = rate_limiter(action='test', limit=5, window_seconds=60)
            await check(_make_request())

        mock_client.expire.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_once_limit_is_exceeded(self):
        """Test that exceeding the limit raises RateLimitExceededException."""
        mock_client = MagicMock()
        mock_client.incr = AsyncMock(return_value=6)
        mock_client.expire = AsyncMock()

        with patch(
            'dependencies.rate_limit._get_redis_client',
            return_value=mock_client,
        ):
            check = rate_limiter(action='test', limit=5, window_seconds=60)
            with pytest.raises(RateLimitExceededException):
                await check(_make_request())

    @pytest.mark.asyncio
    async def test_does_not_reset_expiry_on_every_call(self):
        """Test that EXPIRE is only set on the first request in a window,
        not re-armed on every call (which would let a steady trickle of
        requests keep the window open forever).
        """  # noqa: D205
        mock_client = MagicMock()
        mock_client.incr = AsyncMock(return_value=2)
        mock_client.expire = AsyncMock()

        with patch(
            'dependencies.rate_limit._get_redis_client',
            return_value=mock_client,
        ):
            check = rate_limiter(action='test', limit=5, window_seconds=60)
            await check(_make_request())

        mock_client.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_fails_open_when_redis_is_unreachable(self):
        """Test that a Redis connection error allows the request through
        rather than blocking it - a down rate limiter must not also
        take the protected endpoint down with it.
        """  # noqa: D205
        mock_client = MagicMock()
        mock_client.incr = AsyncMock(
            side_effect=redis.ConnectionError('connection refused')
        )

        with patch(
            'dependencies.rate_limit._get_redis_client',
            return_value=mock_client,
        ):
            check = rate_limiter(action='test', limit=5, window_seconds=60)
            await check(_make_request())  # should not raise
