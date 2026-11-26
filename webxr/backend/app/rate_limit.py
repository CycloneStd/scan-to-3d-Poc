from collections.abc import Callable

from fastapi import HTTPException, Request
from redis import Redis, RedisError

from .config import get_settings

redis_client = Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)


# Install the expiry atomically with the first increment.
_increment = redis_client.register_script("""
local count = redis.call('INCR', KEYS[1])
if count == 1 or redis.call('TTL', KEYS[1]) == -1 then
    redis.call('EXPIRE', KEYS[1], 60)
end
return {count, redis.call('TTL', KEYS[1])}
""")


def rate_limit(scope: str, limit: int | None = None) -> Callable:
    max_requests = limit or get_settings().rate_limit_per_minute

    def dependency(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        key = f"rate:{scope}:{client}"
        try:
            current, ttl = _increment(keys=[key])
        except RedisError as exc:
            if get_settings().environment == "production":
                raise HTTPException(status_code=503, detail="Request protection is temporarily unavailable") from exc
            return
        if current > max_requests:
            raise HTTPException(status_code=429, detail="Too many requests. Please try again shortly.",
                                headers={"Retry-After": str(max(1, ttl))})

    return dependency
