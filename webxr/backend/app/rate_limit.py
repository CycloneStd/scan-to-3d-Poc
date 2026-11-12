from collections.abc import Callable

from fastapi import HTTPException, Request
from redis import Redis, RedisError

from .config import get_settings

redis_client = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=2)


def rate_limit(scope: str, limit: int | None = None) -> Callable:
    max_requests = limit or get_settings().rate_limit_per_minute

    def dependency(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        key = f"rate:{scope}:{client}"
        try:
            current = redis_client.incr(key)
            if current == 1:
                redis_client.expire(key, 60)
        except RedisError as exc:
            if get_settings().environment == "production":
                raise HTTPException(status_code=503, detail="Request protection is temporarily unavailable") from exc
            return
        if current > max_requests:
            raise HTTPException(status_code=429, detail="Too many requests. Please try again shortly.")

    return dependency
