# 这个模块提供 Redis 驱动的后台任务队列，用于承接接口执行、并发测试和 UI 自动化等长任务。
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from redis.exceptions import RedisError

from app.services.api_runner import run_api_load_test, run_api_test, run_api_test_suite
from app.services.database import record_api_test_run, record_ui_test_run
from app.services.failure_agent import analyze_failure
from app.services.redis_service import (
    acquire_lock,
    check_rate_limit,
    get_json,
    get_redis,
    invalidate_cache_namespace,
    is_redis_enabled,
    redis_key,
    release_lock,
    set_json,
)
from app.services.ui_runner import run_ui_test


_worker_tasks: list[asyncio.Task] = []
_stopping = asyncio.Event()


def task_queue_enabled() -> bool:
    return is_redis_enabled() and os.getenv("TASK_QUEUE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def worker_count() -> int:
    value = os.getenv("TASK_WORKER_CONCURRENCY", "2").strip()
    try:
        return max(1, min(int(value), 16))
    except ValueError:
        return 2


def task_submit_limit() -> int:
    value = os.getenv("TASK_SUBMIT_RATE_LIMIT", "30").strip()
    try:
        return max(1, int(value))
    except ValueError:
        return 30


def task_submit_window() -> int:
    value = os.getenv("TASK_SUBMIT_RATE_WINDOW_SECONDS", "60").strip()
    try:
        return max(1, int(value))
    except ValueError:
        return 60


async def start_task_workers() -> None:
    if not task_queue_enabled() or get_redis() is None or _worker_tasks:
        return
    _stopping.clear()
    for index in range(worker_count()):
        _worker_tasks.append(asyncio.create_task(_worker_loop(index + 1), name=f"redis-task-worker-{index + 1}"))


async def stop_task_workers() -> None:
    _stopping.set()
    if not _worker_tasks:
        return
    for task in _worker_tasks:
        task.cancel()
    await asyncio.gather(*_worker_tasks, return_exceptions=True)
    _worker_tasks.clear()


async def queue_status() -> dict[str, Any]:
    client = get_redis()
    if not task_queue_enabled() or client is None:
        return {
            "enabled": False,
            "workers": 0,
            "queued": 0,
            "message": "Redis 任务队列未启用。",
        }
    try:
        return {
            "enabled": True,
            "workers": len(_worker_tasks),
            "configuredWorkers": worker_count(),
            "queued": await client.llen(_queue_key()),
            "message": "Redis 任务队列运行中。" if _worker_tasks else "Redis 已连接，但当前进程未启动任务 worker。",
        }
    except RedisError as exc:
        return {"enabled": True, "workers": len(_worker_tasks), "queued": 0, "message": str(exc)}


async def ensure_submit_allowed(user: dict[str, Any], action: str = "task") -> None:
    user_id = str(user.get("id") or user.get("username") or "anonymous")
    ok, remaining, retry_after = await check_rate_limit(
        redis_key("rate", action, user_id),
        task_submit_limit(),
        task_submit_window(),
    )
    if not ok:
        raise ValueError(f"提交过于频繁，请 {retry_after} 秒后再试。剩余额度：{remaining}")


async def enqueue_task(kind: str, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    client = get_redis()
    if not task_queue_enabled() or client is None:
        raise RuntimeError("Redis 任务队列未启用，请先配置 REDIS_URL 和 REDIS_ENABLED=true。")

    await ensure_submit_allowed(user, "task-submit")
    payload_hash = _payload_hash(kind, payload)
    user_id = str(user.get("id") or user.get("username") or "anonymous")
    lock_key = redis_key("lock", "task", user_id, kind, payload_hash)
    lock_token = await acquire_lock(lock_key, ttl_seconds=180)
    if not lock_token:
        raise ValueError("相同任务正在提交或执行中，请稍后查看任务中心。")

    task_id = f"TASK-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    task = {
        "id": task_id,
        "kind": kind,
        "name": _task_name(kind, payload),
        "status": "pending",
        "progress": 0,
        "message": "任务已进入 Redis 队列。",
        "payload": payload,
        "payloadHash": payload_hash,
        "userId": user_id,
        "username": str(user.get("username") or ""),
        "createdAt": _utc_now(),
        "updatedAt": _utc_now(),
        "startedAt": "",
        "finishedAt": "",
        "result": None,
        "error": "",
        "cancelRequested": False,
        "lockKey": lock_key,
        "lockToken": lock_token,
    }
    await _save_task(task)
    await client.zadd(_recent_key(), {task_id: time.time()})
    await client.lpush(_queue_key(), task_id)
    return _public_task(task)


async def get_task(task_id: str) -> dict[str, Any] | None:
    task = await get_json(_task_key(task_id))
    return _public_task(task) if isinstance(task, dict) else None


async def list_tasks(limit: int = 20, user: dict[str, Any] | None = None) -> dict[str, Any]:
    client = get_redis()
    if not task_queue_enabled() or client is None:
        return {"enabled": False, "items": [], "message": "Redis 任务队列未启用。"}
    safe_limit = max(1, min(limit, 100))
    try:
        ids = await client.zrevrange(_recent_key(), 0, safe_limit * 3)
    except RedisError:
        ids = []
    items = []
    user_id = str(user.get("id") or user.get("username") or "") if user else ""
    for task_id in ids:
        task = await get_json(_task_key(task_id))
        if not isinstance(task, dict):
            continue
        if user_id and task.get("userId") != user_id:
            continue
        items.append(_public_task(task))
        if len(items) >= safe_limit:
            break
    return {"enabled": True, "items": items, "message": "ok"}


async def cancel_task(task_id: str, user: dict[str, Any]) -> dict[str, Any]:
    task = await get_json(_task_key(task_id))
    if not isinstance(task, dict):
        raise KeyError("任务不存在。")
    user_id = str(user.get("id") or user.get("username") or "")
    if task.get("userId") != user_id and user.get("role") != "admin":
        raise PermissionError("无权取消该任务。")
    if task.get("status") in {"success", "failed", "cancelled"}:
        return _public_task(task)
    task["cancelRequested"] = True
    if task.get("status") == "pending":
        task["status"] = "cancelled"
        task["progress"] = 100
        task["message"] = "任务已取消。"
        task["finishedAt"] = _utc_now()
        await _release_task_lock(task)
    else:
        task["message"] = "已请求取消，运行中的任务会在当前执行点结束后停止。"
    task["updatedAt"] = _utc_now()
    await _save_task(task)
    return _public_task(task)


async def _worker_loop(index: int) -> None:
    client = get_redis()
    if client is None:
        return
    while not _stopping.is_set():
        try:
            item = await client.brpop(_queue_key(), timeout=2)
            if not item:
                continue
            _, task_id = item
            await _run_task(str(task_id), index)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(1)


async def _run_task(task_id: str, worker_index: int) -> None:
    task = await get_json(_task_key(task_id))
    if not isinstance(task, dict):
        return
    if task.get("cancelRequested"):
        task.update(status="cancelled", progress=100, message="任务已取消。", finishedAt=_utc_now(), updatedAt=_utc_now())
        await _save_task(task)
        await _release_task_lock(task)
        return

    task.update(status="running", progress=10, message=f"Worker {worker_index} 已开始执行。", startedAt=_utc_now(), updatedAt=_utc_now())
    await _save_task(task)

    try:
        result = await _execute_task(task)
        task.update(
            status="success" if result.get("passed", True) else "failed",
            progress=100,
            message="任务执行完成。" if result.get("passed", True) else "任务执行完成，但存在失败项。",
            result=result,
            error=str(result.get("error") or ""),
            finishedAt=_utc_now(),
            updatedAt=_utc_now(),
        )
    except Exception as exc:
        task.update(
            status="failed",
            progress=100,
            message="任务执行失败。",
            error=str(exc),
            finishedAt=_utc_now(),
            updatedAt=_utc_now(),
        )
    await _save_task(task)
    await _release_task_lock(task)


async def _execute_task(task: dict[str, Any]) -> dict[str, Any]:
    kind = str(task.get("kind") or "")
    payload = task.get("payload") or {}
    if kind == "api_run":
        result = await run_api_test(payload)
        if not result.get("passed"):
            result["failureAnalysis"] = analyze_failure(result)
        result["historyStatus"] = await asyncio.to_thread(record_api_test_run, result)
        await invalidate_cache_namespace("api-runs")
        return result
    if kind == "api_suite":
        result = await run_api_test_suite(payload)
        if not result.get("passed"):
            result["failureAnalysis"] = analyze_failure(result)
        result["historyStatus"] = await asyncio.to_thread(record_api_test_run, result)
        await invalidate_cache_namespace("api-runs")
        return result
    if kind == "api_load":
        result = await run_api_load_test(payload)
        if not result.get("passed"):
            result["failureAnalysis"] = analyze_failure(result)
        result["historyStatus"] = await asyncio.to_thread(record_api_test_run, result)
        await invalidate_cache_namespace("api-runs")
        return result
    if kind == "ui_run":
        result = await run_ui_test(payload)
        result["historyStatus"] = await asyncio.to_thread(record_ui_test_run, result)
        await invalidate_cache_namespace("ui-runs")
        return result
    raise ValueError(f"未知任务类型：{kind}")


async def _save_task(task: dict[str, Any]) -> None:
    await set_json(_task_key(task["id"]), task, ttl_seconds=_task_ttl_seconds())


async def _release_task_lock(task: dict[str, Any]) -> None:
    lock_key = str(task.get("lockKey") or "")
    lock_token = str(task.get("lockToken") or "")
    if lock_key and lock_token:
        await release_lock(lock_key, lock_token)


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id"),
        "kind": task.get("kind"),
        "name": task.get("name"),
        "status": task.get("status"),
        "progress": task.get("progress", 0),
        "message": task.get("message", ""),
        "createdAt": task.get("createdAt", ""),
        "updatedAt": task.get("updatedAt", ""),
        "startedAt": task.get("startedAt", ""),
        "finishedAt": task.get("finishedAt", ""),
        "username": task.get("username", ""),
        "result": task.get("result"),
        "error": task.get("error", ""),
    }


def _task_name(kind: str, payload: dict[str, Any]) -> str:
    if payload.get("name"):
        return str(payload["name"])
    labels = {
        "api_run": "接口执行任务",
        "api_suite": "接口用例集任务",
        "api_load": "接口并发任务",
        "ui_run": "UI 自动化任务",
    }
    return labels.get(kind, "测试执行任务")


def _payload_hash(kind: str, payload: dict[str, Any]) -> str:
    raw = json.dumps({"kind": kind, "payload": payload}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _queue_key() -> str:
    return redis_key("tasks", "queue")


def _recent_key() -> str:
    return redis_key("tasks", "recent")


def _task_key(task_id: str) -> str:
    return redis_key("tasks", "item", task_id)


def _task_ttl_seconds() -> int:
    value = os.getenv("TASK_RESULT_TTL_SECONDS", "86400").strip()
    try:
        return max(300, int(value))
    except ValueError:
        return 86400


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
