from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx


ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
MAX_TIMEOUT_SECONDS = 30.0
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_PREVIEW_CHARS = 12000


async def run_api_test(payload: dict[str, Any]) -> dict[str, Any]:
    method = str(payload.get("method") or "GET").strip().upper()
    url = str(payload.get("url") or "").strip()
    name = str(payload.get("name") or "").strip()[:255] or f"{method} {url}"
    headers = _normalize_headers(payload.get("headers") or {})
    body = str(payload.get("body") or "")
    expected_status = _normalize_expected_status(payload.get("expected_status"))
    expected_contains = str(payload.get("expected_contains") or "").strip()
    timeout_seconds = _normalize_timeout(payload.get("timeout_seconds"))

    _validate_request(method=method, url=url, body=body)

    run_id = f"API-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    started_at = datetime.utcnow().isoformat() + "Z"
    started = time.perf_counter()
    actual_status: int | None = None
    response_headers: dict[str, str] = {}
    response_body_preview = ""
    error = ""
    assertions: list[dict[str, Any]] = []

    try:
        request_kwargs: dict[str, Any] = {"headers": headers}
        if body:
            request_kwargs["content"] = body.encode("utf-8")

        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            response = await client.request(method, url, **request_kwargs)

        actual_status = response.status_code
        response_headers = {key: value for key, value in response.headers.items()}
        response_text = response.text
        response_body_preview = _preview(response_text)
        assertions.append({"name": "请求可达", "passed": True, "message": "HTTP 请求已完成"})

        if expected_status is not None:
            assertions.append(
                {
                    "name": "状态码匹配",
                    "passed": actual_status == expected_status,
                    "message": f"期望 {expected_status}，实际 {actual_status}",
                }
            )

        if expected_contains:
            assertions.append(
                {
                    "name": "响应内容包含",
                    "passed": expected_contains in response_text,
                    "message": f"查找文本：{expected_contains}",
                }
            )
    except httpx.TimeoutException as exc:
        error = f"请求超时：{exc}"
    except httpx.RequestError as exc:
        error = f"请求失败：{exc}"

    duration_ms = int((time.perf_counter() - started) * 1000)
    if error:
        assertions.append({"name": "请求可达", "passed": False, "message": error})

    passed = bool(assertions) and all(item.get("passed") for item in assertions)
    return {
        "runId": run_id,
        "createdAt": started_at,
        "name": name,
        "request": {
            "method": method,
            "url": url,
            "headers": headers,
            "body": body,
            "timeoutSeconds": timeout_seconds,
        },
        "expected": {
            "status": expected_status,
            "contains": expected_contains,
        },
        "response": {
            "statusCode": actual_status,
            "durationMs": duration_ms,
            "headers": response_headers,
            "bodyPreview": response_body_preview,
        },
        "assertions": assertions,
        "passed": passed,
        "error": error,
    }


def _validate_request(*, method: str, url: str, body: str) -> None:
    if method not in ALLOWED_METHODS:
        raise ValueError(f"暂不支持 {method} 方法。")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("接口地址必须是完整的 http:// 或 https:// URL。")
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError("请求体超过 2MB，当前执行器会拒绝过大的请求体。")


def _normalize_headers(headers: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if not isinstance(headers, dict):
        return normalized
    for key, value in headers.items():
        header_name = str(key).strip()
        if not header_name or "\r" in header_name or "\n" in header_name:
            continue
        normalized[header_name] = str(value)
    return normalized


def _normalize_timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        timeout = 10.0
    return max(1.0, min(timeout, MAX_TIMEOUT_SECONDS))


def _normalize_expected_status(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        status = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("期望状态码必须是 100-599 之间的数字。") from exc
    if status < 100 or status > 599:
        raise ValueError("期望状态码必须是 100-599 之间的数字。")
    return status


def _preview(value: str) -> str:
    if len(value) <= MAX_RESPONSE_PREVIEW_CHARS:
        return value
    return value[:MAX_RESPONSE_PREVIEW_CHARS] + "\n...响应内容已截断"
