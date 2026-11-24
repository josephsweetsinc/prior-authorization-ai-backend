"""Per-IP rate limiting for auth endpoints prone to brute-forcing."""

import logging
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache

import redis.asyncio as redis
from fastapi import Request

from config.settings import Settings
from exceptions import RateLimitExceededException

logger = logging.getLogger(__name__)

REDIS_TIMEOUT_SECONDS = 1.0


@lru_cache(maxsize=1)
def _get_redis_client() -> redis.Redis:
    """Get a process-wide async Redis client singleton for rate limiting.

    Reuses the same Redis instance Celery already uses as its broker -
    a fixed-window counter needs nothing more than INCR/EXPIRE, so this
    adds no new infrastructure. A short timeout keeps a slow/unreachable
    Redis from stalling every login attempt behind it.

    Returns:
        redis.Redis: Shared async Redis client.

    """
    settings = Settings.load()
    # redis-py's own type stubs leave from_url's return untyped.
    return redis.from_url(  # type: ignore[no-untyped-call,no-any-return]
        settings.redis_settings.url(),
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
    )


def _client_ip(request: Request) -> str:
    """Get the real client IP, accounting for the nginx reverse proxy.

    Uvicorn sees every request as coming from nginx itself (127.0.0.1)
    unless the X-Real-IP header nginx sets
    (`proxy_set_header X-Real-IP $remote_addr` - see
    terraform/modules/ec2's nginx config) is read instead. Using
    request.client.host directly would put every real client in the
    same rate-limit bucket.

    Args:
        request: Incoming FastAPI request.

    Returns:
        str: Best-effort client IP address.

    """
    real_ip = request.headers.get('x-real-ip')
    if real_ip:
        return real_ip
    forwarded_for = request.headers.get('x-forwarded-for')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'


def rate_limiter(
    *,
    action: str,
    limit: int,
    window_seconds: int,
) -> Callable[[Request], Awaitable[None]]:
    """Build a FastAPI dependency enforcing a per-IP rate limit.

    Uses a fixed-window counter in Redis (INCR, with EXPIRE set once
    per window) keyed by action + client IP + current window. Backed
    by Redis rather than in-memory state, so the limit is shared
    correctly across paai_api/worker processes, not per-process.

    Fails open (allows the request through, logging a warning)
    instead of raising if Redis itself is unreachable - a rate
    limiter going down should not also take login down with it.

    Args:
        action: Short name identifying what's being limited (e.g.
            'login'), used as part of the Redis key so different
            endpoints don't share a counter.
        limit: Maximum requests allowed per window.
        window_seconds: Window length in seconds.

    Returns:
        An async FastAPI dependency callable that raises
        RateLimitExceededException once the limit is exceeded within
        the current window.

    """

    async def _check(request: Request) -> None:
        window = int(time.time()) // window_seconds
        key = f'ratelimit:{action}:{_client_ip(request)}:{window}'
        try:
            client = _get_redis_client()
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, window_seconds)
        except redis.RedisError:
            logger.warning(
                'Rate limiter could not reach Redis for action=%s; '
                'allowing the request through',
                action,
            )
            return
        if count > limit:
            raise RateLimitExceededException

    return _check
