# 这个模块封装 Redis 连接、缓存、限流和分布式锁，Redis 未启用时保持静默降级。
from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import redis.asyncio as redis
from redis.exceptions import RedisError


T = TypeVar("T")

_client: redis.Redis | None = None
_last_error = ""


def is_redis_enabled() -> bool:
    explicit = os.getenv("REDIS_ENABLED", "").strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    if explicit in {"0", "false", "no", "off"}:
        return False
    return bool(os.getenv("REDIS_URL", "").strip())


def redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip() or "redis://127.0.0.1:6379/0"


def key_prefix() -> str:
    return os.getenv("REDIS_KEY_PREFIX", "ai-test").strip() or "ai-test"


def redis_key(*parts: Any) -> str:
    safe_parts = [str(part).strip().replace(" ", "_") for part in parts if str(part).strip()]
    return ":".join([key_prefix(), *safe_parts])


async def init_redis() -> bool:
    global _client, _last_error
    if not is_redis_enabled():
        _last_error = ""
        _client = None
        return False
    try:
        _client = redis.from_url(redis_url(), encoding="utf-8", decode_responses=True)
        await _client.ping()
        _last_error = ""
        return True
    except RedisError as exc:
        _last_error = str(exc)
        _client = None
        return False


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_redis() -> redis.Redis | None:
    return _client


async def redis_status() -> dict[str, Any]:
    if not is_redis_enabled():
        return {"enabled": False, "connected": False, "message": "Redis 未启用。"}
    if _client is None:
        return {"enabled": True, "connected": False, "message": _last_error or "Redis 未连接。"}
    try:
        pong = await _client.ping()
        return {
            "enabled": True,
            "connected": bool(pong),
            "message": "Redis 连接正常。" if pong else "Redis ping 失败。",
            "url": _safe_url(redis_url()),
        }
    except RedisError as exc:
        return {"enabled": True, "connected": False, "message": str(exc), "url": _safe_url(redis_url())}


async def get_json(key: str) -> Any | None:
    client = get_redis()
    if client is None:
        return None
    try:
        raw = await client.get(key)
        if not raw:
            return None
        return json.loads(raw)
    except (RedisError, json.JSONDecodeError):
        return None


async def set_json(key: str, value: Any, ttl_seconds: int = 60) -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        await client.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=max(1, ttl_seconds))
        return True
    except RedisError:
        return False


async def cached_json(key: str, ttl_seconds: int, loader: Callable[[], Awaitable[T]]) -> T:
    cached = await get_json(key)
    if cached is not None:
        if isinstance(cached, dict):
            cached.setdefault("cache", {"hit": True, "provider": "redis"})
        return cached
    value = await loader()
    await set_json(key, value, ttl_seconds)
    return value


async def delete_pattern(pattern: str) -> int:
    client = get_redis()
    if client is None:
        return 0
    removed = 0
    try:
        async for key in client.scan_iter(match=pattern, count=100):
            removed += await client.delete(key)
    except RedisError:
        return removed
    return removed


async def invalidate_cache_namespace(namespace: str) -> int:
    return await delete_pattern(redis_key("cache", namespace, "*"))


async def check_rate_limit(key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
    client = get_redis()
    if client is None or limit <= 0:
        return True, limit, window_seconds
    safe_window = max(1, window_seconds)
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, safe_window)
        ttl = await client.ttl(key)
        remaining = max(0, limit - int(count))
        return int(count) <= limit, remaining, ttl if ttl > 0 else safe_window
    except RedisError:
        return True, limit, safe_window


async def acquire_lock(key: str, ttl_seconds: int = 120) -> str | None:
    client = get_redis()
    if client is None:
        return uuid.uuid4().hex
    token = uuid.uuid4().hex
    try:
        ok = await client.set(key, token, nx=True, ex=max(1, ttl_seconds))
        return token if ok else None
    except RedisError:
        return token


async def release_lock(key: str, token: str) -> bool:
    client = get_redis()
    if client is None:
        return True
    script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
      return redis.call("del", KEYS[1])
    end
    return 0
    """
    try:
        return bool(await client.eval(script, 1, key, token))
    except RedisError:
        return False


def now_ms() -> int:
    return int(time.time() * 1000)


def _safe_url(value: str) -> str:
    if "@" not in value:
        return value
    scheme, _, rest = value.partition("://")
    _, _, host_part = rest.rpartition("@")
    return f"{scheme}://***@{host_part}"
