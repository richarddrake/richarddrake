from __future__ import annotations

import asyncio
import base64
import json
import re
import statistics
import time
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.database import run_readonly_query


ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
MAX_TIMEOUT_SECONDS = 30.0
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_RESPONSE_PREVIEW_CHARS = 12000
MAX_SUITE_STEPS = 30
MAX_LOAD_REPEAT = 100
MAX_LOAD_CONCURRENCY = 20
VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][\w.-]*)\s*\}\}")


async def run_api_test(payload: dict[str, Any], runtime_variables: dict[str, Any] | None = None) -> dict[str, Any]:
    variables = {
        **_as_dict(payload.get("variables")),
        **_as_dict(runtime_variables),
    }
    prepared = _prepare_request(payload, variables)
    _validate_request(method=prepared["method"], url=prepared["url"], body=prepared["body"])

    run_id = _make_run_id("API")
    started_at = datetime.utcnow().isoformat() + "Z"
    started = time.perf_counter()
    actual_status: int | None = None
    response_headers: dict[str, str] = {}
    response_body_preview = ""
    response_text = ""
    response_json: Any = None
    error = ""
    assertions: list[dict[str, Any]] = []
    extractions: list[dict[str, Any]] = []
    database_checks: list[dict[str, Any]] = []

    try:
        request_kwargs = _build_httpx_kwargs(prepared)
        async with httpx.AsyncClient(timeout=prepared["timeoutSeconds"], follow_redirects=True) as client:
            response = await client.request(prepared["method"], prepared["url"], **request_kwargs)

        actual_status = response.status_code
        response_headers = {key: value for key, value in response.headers.items()}
        response_text = response.text
        response_json = _try_json(response_text)
        response_body_preview = _preview(response_text)
        assertions.append(_assertion("请求可达", True, "HTTP 请求已完成", category="connectivity"))
    except (ValueError, json.JSONDecodeError) as exc:
        error = f"请求配置错误：{exc}"
    except httpx.TimeoutException as exc:
        error = f"请求超时：{exc}"
    except httpx.RequestError as exc:
        error = f"请求失败：{exc}"

    duration_ms = int((time.perf_counter() - started) * 1000)
    if error:
        assertions.append(_assertion("请求可达", False, error, category="connectivity"))
    else:
        assertions.extend(
            _evaluate_builtin_assertions(
                expected_status=prepared["expectedStatus"],
                expected_contains=prepared["expectedContains"],
                max_response_ms=prepared["maxResponseMs"],
                actual_status=actual_status,
                response_text=response_text,
                duration_ms=duration_ms,
            )
        )
        context = {
            "statusCode": actual_status,
            "durationMs": duration_ms,
            "headers": response_headers,
            "body": response_text,
            "json": response_json,
            "variables": variables,
        }
        assertions.extend(_evaluate_custom_assertions(prepared["assertions"], context))
        assertions.extend(_evaluate_schema_assertions(prepared["schema"], response_json))

        extractions = _apply_extractors(prepared["extractors"], context, variables)
        db_assertions = _render_value(prepared["databaseAssertions"], variables)
        database_checks = await _evaluate_database_assertions(db_assertions, variables)
        assertions.extend(database_checks)

    passed = bool(assertions) and all(item.get("passed") for item in assertions)
    return {
        "runId": run_id,
        "createdAt": started_at,
        "name": prepared["name"],
        "runType": "single",
        "request": {
            "method": prepared["method"],
            "url": prepared["url"],
            "headers": prepared["headers"],
            "body": prepared["body"],
            "bodyMode": prepared["bodyMode"],
            "formFields": prepared["formFields"],
            "files": [_safe_file_summary(item) for item in prepared["files"]],
            "timeoutSeconds": prepared["timeoutSeconds"],
        },
        "expected": {
            "status": prepared["expectedStatus"],
            "contains": prepared["expectedContains"],
            "maxResponseMs": prepared["maxResponseMs"],
        },
        "response": {
            "statusCode": actual_status,
            "durationMs": duration_ms,
            "headers": response_headers,
            "bodyPreview": response_body_preview,
        },
        "assertions": assertions,
        "extractions": extractions,
        "databaseChecks": database_checks,
        "variables": variables,
        "summary": _summarize_assertions(assertions),
        "passed": passed,
        "error": error,
    }


async def run_api_test_suite(payload: dict[str, Any]) -> dict[str, Any]:
    steps = payload.get("steps") or []
    if not isinstance(steps, list) or not steps:
        raise ValueError("用例集至少需要 1 个 step。")
    if len(steps) > MAX_SUITE_STEPS:
        raise ValueError(f"用例集最多支持 {MAX_SUITE_STEPS} 个 step。")

    variables = _as_dict(payload.get("variables"))
    stop_on_failure = bool(payload.get("stop_on_failure") or payload.get("stopOnFailure"))
    run_id = _make_run_id("SUITE")
    started_at = datetime.utcnow().isoformat() + "Z"
    started = time.perf_counter()
    step_results: list[dict[str, Any]] = []

    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"第 {index} 个 step 必须是对象。")
        step_payload = {
            **step,
            "name": step.get("name") or f"Step {index}",
            "variables": variables,
        }
        result = await run_api_test(step_payload, variables)
        result["stepIndex"] = index
        step_results.append(result)
        variables.update(_as_dict(result.get("variables")))
        if stop_on_failure and not result.get("passed"):
            break

    duration_ms = int((time.perf_counter() - started) * 1000)
    assertions = [
        _assertion(
            f"{item.get('stepIndex')}. {item.get('name')}",
            bool(item.get("passed")),
            f"{item.get('request', {}).get('method')} {item.get('request', {}).get('url')}",
            category="suite",
        )
        for item in step_results
    ]
    passed = len(step_results) == len(steps) and all(item.get("passed") for item in step_results)
    return {
        "runId": run_id,
        "createdAt": started_at,
        "name": str(payload.get("name") or "接口用例集").strip()[:255],
        "runType": "suite",
        "request": {
            "method": "SUITE",
            "url": f"{len(steps)} steps",
            "headers": variables,
            "body": _json_dumps(steps),
            "timeoutSeconds": None,
        },
        "expected": {
            "status": None,
            "contains": "",
            "maxResponseMs": None,
        },
        "response": {
            "statusCode": None,
            "durationMs": duration_ms,
            "headers": {"stepCount": str(len(step_results))},
            "bodyPreview": _preview(_json_dumps(_suite_report(step_results))),
        },
        "assertions": assertions,
        "steps": step_results,
        "variables": variables,
        "summary": {
            "totalSteps": len(steps),
            "executedSteps": len(step_results),
            "passedSteps": sum(1 for item in step_results if item.get("passed")),
            "failedSteps": sum(1 for item in step_results if not item.get("passed")),
            "durationMs": duration_ms,
        },
        "passed": passed,
        "error": "" if passed else "用例集中存在失败步骤。",
    }


async def run_api_load_test(payload: dict[str, Any]) -> dict[str, Any]:
    repeat = _bounded_int(payload.get("repeat"), default=10, minimum=1, maximum=MAX_LOAD_REPEAT)
    concurrency = _bounded_int(payload.get("concurrency"), default=3, minimum=1, maximum=MAX_LOAD_CONCURRENCY)
    run_id = _make_run_id("LOAD")
    started_at = datetime.utcnow().isoformat() + "Z"
    started = time.perf_counter()
    semaphore = asyncio.Semaphore(concurrency)

    async def run_once(index: int) -> dict[str, Any]:
        async with semaphore:
            result = await run_api_test(
                {
                    **payload,
                    "name": f"{payload.get('name') or 'load'} #{index}",
                    "database_assertions": [],
                    "databaseAssertions": [],
                    "extractors": [],
                }
            )
            return {
                "index": index,
                "passed": result.get("passed"),
                "durationMs": result.get("response", {}).get("durationMs") or 0,
                "statusCode": result.get("response", {}).get("statusCode"),
                "error": result.get("error") or "",
            }

    results = await asyncio.gather(*(run_once(index) for index in range(1, repeat + 1)))
    duration_ms = int((time.perf_counter() - started) * 1000)
    durations = [item["durationMs"] for item in results if item["durationMs"] is not None]
    passed_count = sum(1 for item in results if item["passed"])
    failed_count = repeat - passed_count
    metrics = _load_metrics(durations, repeat, concurrency, duration_ms, passed_count, failed_count)
    assertions = [
        _assertion("并发执行完成", failed_count == 0, f"通过 {passed_count}/{repeat}，失败 {failed_count}", category="load")
    ]
    return {
        "runId": run_id,
        "createdAt": started_at,
        "name": str(payload.get("name") or "接口并发测试").strip()[:255],
        "runType": "load",
        "request": {
            "method": "LOAD",
            "url": str(payload.get("url") or ""),
            "headers": _as_dict(payload.get("headers")),
            "body": str(payload.get("body") or ""),
            "timeoutSeconds": payload.get("timeout_seconds") or payload.get("timeoutSeconds") or 10,
        },
        "expected": {
            "status": payload.get("expected_status") or payload.get("expectedStatus"),
            "contains": payload.get("expected_contains") or payload.get("expectedContains") or "",
            "maxResponseMs": payload.get("max_response_ms") or payload.get("maxResponseMs"),
        },
        "response": {
            "statusCode": None,
            "durationMs": duration_ms,
            "headers": {"repeat": str(repeat), "concurrency": str(concurrency)},
            "bodyPreview": _preview(_json_dumps({"metrics": metrics, "samples": results[:20]})),
        },
        "assertions": assertions,
        "loadResults": results,
        "summary": metrics,
        "passed": failed_count == 0,
        "error": "" if failed_count == 0 else "并发执行中存在失败请求。",
    }


def _prepare_request(payload: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    method = _render_text(payload.get("method") or "GET", variables).strip().upper()
    url = _render_text(payload.get("url") or "", variables).strip()
    name = _render_text(payload.get("name") or "", variables).strip()[:255] or f"{method} {url}"
    headers = _normalize_headers(_render_value(payload.get("headers") or {}, variables))
    body = _render_text(payload.get("body") or "", variables)
    body_mode = str(payload.get("body_mode") or payload.get("bodyMode") or "raw").strip().lower()
    form_fields = _render_value(payload.get("form_fields") or payload.get("formFields") or {}, variables)
    files = _render_value(payload.get("files") or [], variables)
    expected_status = _normalize_expected_status(payload.get("expected_status") or payload.get("expectedStatus"))
    expected_contains = _render_text(payload.get("expected_contains") or payload.get("expectedContains") or "", variables).strip()
    timeout_seconds = _normalize_timeout(payload.get("timeout_seconds") or payload.get("timeoutSeconds"))
    max_response_ms = _optional_float(payload.get("max_response_ms") or payload.get("maxResponseMs"))
    assertions = _as_list(payload.get("assertions"))
    extractors = _as_list(payload.get("extractors"))
    schema = payload.get("json_schema") or payload.get("jsonSchema") or payload.get("schema")
    database_assertions = _as_list(payload.get("database_assertions") or payload.get("databaseAssertions"))
    return {
        "name": name,
        "method": method,
        "url": url,
        "headers": headers,
        "body": body,
        "bodyMode": body_mode,
        "formFields": form_fields if isinstance(form_fields, dict) else {},
        "files": files if isinstance(files, list) else [],
        "expectedStatus": expected_status,
        "expectedContains": expected_contains,
        "timeoutSeconds": timeout_seconds,
        "maxResponseMs": max_response_ms,
        "assertions": assertions,
        "extractors": extractors,
        "schema": schema,
        "databaseAssertions": database_assertions,
    }


def _build_httpx_kwargs(prepared: dict[str, Any]) -> dict[str, Any]:
    headers = dict(prepared["headers"])
    body_mode = prepared["bodyMode"]
    kwargs: dict[str, Any] = {"headers": headers}

    if body_mode == "json":
        kwargs["json"] = json.loads(prepared["body"]) if prepared["body"].strip() else {}
    elif body_mode in {"form", "x-www-form-urlencoded"}:
        kwargs["data"] = prepared["formFields"] or _parse_form_text(prepared["body"])
    elif body_mode == "multipart":
        kwargs["data"] = prepared["formFields"]
        kwargs["files"] = _build_files(prepared["files"])
    elif prepared["body"]:
        kwargs["content"] = prepared["body"].encode("utf-8")

    return kwargs


def _validate_request(*, method: str, url: str, body: str) -> None:
    if method not in ALLOWED_METHODS:
        raise ValueError(f"暂不支持 {method} 方法。")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("接口地址必须是完整的 http:// 或 https:// URL。")
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError("请求体超过 2MB，当前执行器会拒绝过大的请求体。")


def _evaluate_builtin_assertions(
    *,
    expected_status: int | None,
    expected_contains: str,
    max_response_ms: float | None,
    actual_status: int | None,
    response_text: str,
    duration_ms: int,
) -> list[dict[str, Any]]:
    assertions: list[dict[str, Any]] = []
    if expected_status is not None:
        assertions.append(
            _assertion(
                "状态码匹配",
                actual_status == expected_status,
                f"期望 {expected_status}，实际 {actual_status}",
                category="status",
                actual=actual_status,
                expected=expected_status,
            )
        )
    if expected_contains:
        assertions.append(
            _assertion(
                "响应内容包含",
                expected_contains in response_text,
                f"查找文本：{expected_contains}",
                category="body",
                actual=_preview(response_text),
                expected=expected_contains,
            )
        )
    if max_response_ms is not None:
        assertions.append(
            _assertion(
                "响应时间达标",
                duration_ms <= max_response_ms,
                f"期望 <= {max_response_ms} ms，实际 {duration_ms} ms",
                category="performance",
                actual=duration_ms,
                expected=max_response_ms,
            )
        )
    return assertions


def _evaluate_custom_assertions(assertions: list[Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, spec in enumerate(assertions, start=1):
        if not isinstance(spec, dict):
            results.append(_assertion(f"自定义断言 {index}", False, "断言必须是对象", category="custom"))
            continue
        try:
            actual = _read_assertion_source(spec, context)
            operator = str(spec.get("operator") or spec.get("op") or "equals").strip()
            expected = spec.get("expected")
            passed, message = _compare(actual, operator, expected)
            results.append(
                _assertion(
                    str(spec.get("name") or f"自定义断言 {index}"),
                    passed,
                    message,
                    category=str(spec.get("category") or spec.get("source") or "custom"),
                    actual=actual,
                    expected=expected,
                    operator=operator,
                )
            )
        except Exception as exc:
            results.append(_assertion(str(spec.get("name") or f"自定义断言 {index}"), False, str(exc), category="custom"))
    return results


def _read_assertion_source(spec: dict[str, Any], context: dict[str, Any]) -> Any:
    source = str(spec.get("source") or "json").strip().lower()
    if source in {"status", "statuscode"}:
        return context.get("statusCode")
    if source in {"time", "duration", "durationms"}:
        return context.get("durationMs")
    if source == "header":
        return _get_header(context.get("headers") or {}, str(spec.get("header") or spec.get("path") or spec.get("name") or ""))
    if source in {"body", "text"}:
        body = context.get("body") or ""
        if spec.get("regex"):
            match = re.search(str(spec.get("regex")), body)
            return match.group(1) if match and match.groups() else (match.group(0) if match else None)
        return body
    if source == "variable":
        return _resolve_variable(context.get("variables") or {}, str(spec.get("path") or spec.get("name") or ""))
    path = str(spec.get("path") or "$")
    return _json_path(context.get("json"), path)


def _evaluate_schema_assertions(schema: Any, response_json: Any) -> list[dict[str, Any]]:
    if not schema:
        return []
    if response_json is None:
        return [_assertion("JSON Schema", False, "响应体不是合法 JSON，无法进行 Schema 校验", category="schema")]
    errors = _validate_schema(response_json, schema)
    return [_assertion("JSON Schema", not errors, "; ".join(errors[:8]) or "Schema 校验通过", category="schema")]


def _apply_extractors(specs: list[Any], context: dict[str, Any], variables: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        if not isinstance(spec, dict):
            results.append({"name": f"extract_{index}", "passed": False, "message": "提取器必须是对象"})
            continue
        variable_name = str(spec.get("variable") or spec.get("name") or "").strip()
        if not variable_name:
            results.append({"name": f"extract_{index}", "passed": False, "message": "提取器缺少变量名"})
            continue
        try:
            value = _read_assertion_source(spec, context)
            if value is None and "default" in spec:
                value = spec.get("default")
            variables[variable_name] = value
            results.append({"name": variable_name, "passed": value is not None, "value": value, "message": "变量已提取" if value is not None else "未提取到值"})
        except Exception as exc:
            results.append({"name": variable_name, "passed": False, "message": str(exc)})
    return results


async def _evaluate_database_assertions(specs: list[Any], variables: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        if not isinstance(spec, dict):
            results.append(_assertion(f"数据库校验 {index}", False, "数据库校验必须是对象", category="database"))
            continue
        name = str(spec.get("name") or f"数据库校验 {index}")
        sql = _render_text(spec.get("sql") or "", variables).strip()
        if not sql:
            results.append(_assertion(name, False, "缺少 SQL", category="database"))
            continue
        try:
            query_result = await asyncio.to_thread(run_readonly_query, sql)
            if not query_result.get("ok"):
                results.append(_assertion(name, False, query_result.get("message") or "数据库查询失败", category="database"))
                continue
            actual = _database_actual_value(query_result, spec)
            operator = str(spec.get("operator") or spec.get("op") or "equals")
            expected = spec.get("expected")
            passed, message = _compare(actual, operator, expected)
            results.append(
                _assertion(name, passed, message, category="database", actual=actual, expected=expected, operator=operator)
                | {"rows": query_result.get("rows", [])[:5], "rowCount": query_result.get("rowCount", 0)}
            )
        except Exception as exc:
            results.append(_assertion(name, False, str(exc), category="database"))
    return results


def _database_actual_value(query_result: dict[str, Any], spec: dict[str, Any]) -> Any:
    rows = query_result.get("rows") or []
    if str(spec.get("actual") or "").lower() == "rowcount":
        return query_result.get("rowCount", 0)
    if spec.get("path"):
        return _json_path(rows, str(spec.get("path")))
    if not rows:
        return None
    first = rows[0]
    if not isinstance(first, dict) or not first:
        return first
    if spec.get("column"):
        return first.get(str(spec.get("column")))
    return next(iter(first.values()))


def _compare(actual: Any, operator: str, expected: Any) -> tuple[bool, str]:
    op = operator.strip().lower().replace("_", "").replace("-", "")
    if op in {"exists", "exist"}:
        return actual is not None, f"实际值 {'存在' if actual is not None else '不存在'}"
    if op in {"notexists", "missing"}:
        return actual is None, f"实际值 {'不存在' if actual is None else '存在'}"
    if op in {"equals", "eq", "="}:
        passed = _stringify(actual) == _stringify(expected)
    elif op in {"notequals", "ne", "!="}:
        passed = _stringify(actual) != _stringify(expected)
    elif op == "contains":
        passed = _stringify(expected) in _stringify(actual)
    elif op == "notcontains":
        passed = _stringify(expected) not in _stringify(actual)
    elif op in {"gt", "greaterthan", ">"}:
        passed = _as_float(actual) > _as_float(expected)
    elif op in {"gte", "greaterthanequal", ">="}:
        passed = _as_float(actual) >= _as_float(expected)
    elif op in {"lt", "lessthan", "<"}:
        passed = _as_float(actual) < _as_float(expected)
    elif op in {"lte", "lessthanequal", "<="}:
        passed = _as_float(actual) <= _as_float(expected)
    elif op == "regex":
        passed = re.search(str(expected), _stringify(actual)) is not None
    elif op == "in":
        candidates = expected if isinstance(expected, list) else str(expected).split(",")
        passed = _stringify(actual) in [_stringify(item) for item in candidates]
    elif op == "startswith":
        passed = _stringify(actual).startswith(_stringify(expected))
    elif op == "endswith":
        passed = _stringify(actual).endswith(_stringify(expected))
    elif op == "type":
        passed = _type_name(actual) == str(expected).lower()
    elif op == "length":
        passed = len(actual if isinstance(actual, (list, dict, str)) else _stringify(actual)) == int(expected)
    else:
        raise ValueError(f"不支持的断言操作符：{operator}")
    return passed, f"实际：{_compact_value(actual)}；期望：{_compact_value(expected)}；操作符：{operator}"


def _json_path(data: Any, path: str) -> Any:
    if path in {"", "$"}:
        return data
    if not path.startswith("$"):
        path = "$." + path
    tokens = _parse_json_path(path)
    current = [data]
    for token in tokens:
        next_values: list[Any] = []
        for item in current:
            if token == "*":
                if isinstance(item, dict):
                    next_values.extend(item.values())
                elif isinstance(item, list):
                    next_values.extend(item)
            elif isinstance(token, int):
                if isinstance(item, list) and -len(item) <= token < len(item):
                    next_values.append(item[token])
            elif isinstance(item, dict) and token in item:
                next_values.append(item[token])
        current = next_values
    if not current:
        return None
    return current[0] if len(current) == 1 else current


def _parse_json_path(path: str) -> list[str | int]:
    text = path[1:].lstrip(".")
    tokens: list[str | int] = []
    index = 0
    buffer = ""
    while index < len(text):
        char = text[index]
        if char == ".":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            index += 1
            continue
        if char == "[":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            end = text.find("]", index)
            if end == -1:
                raise ValueError(f"JSONPath 不合法：{path}")
            raw = text[index + 1 : end].strip().strip("'\"")
            tokens.append("*" if raw == "*" else int(raw) if raw.lstrip("-").isdigit() else raw)
            index = end + 1
            continue
        buffer += char
        index += 1
    if buffer:
        tokens.append(buffer)
    return tokens


def _validate_schema(value: Any, schema: Any, path: str = "$") -> list[str]:
    if not isinstance(schema, dict):
        return []
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type and _type_name(value) != str(expected_type).lower():
        return [f"{path} 类型应为 {expected_type}，实际为 {_type_name(value)}"]
    if "enum" in schema and value not in schema.get("enum", []):
        errors.append(f"{path} 不在枚举范围内")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key} 缺失")
        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value:
                    errors.extend(_validate_schema(value[key], child_schema, f"{path}.{key}"))
    if isinstance(value, list) and schema.get("items"):
        for index, item in enumerate(value[:50]):
            errors.extend(_validate_schema(item, schema["items"], f"{path}[{index}]"))
    return errors


def _render_value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _render_text(value, variables)
    if isinstance(value, dict):
        return {key: _render_value(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_value(item, variables) for item in value]
    return value


def _render_text(value: Any, variables: dict[str, Any]) -> str:
    text = str(value or "")

    def replace(match: re.Match[str]) -> str:
        resolved = _resolve_variable(variables, match.group(1))
        return "" if resolved is None else str(resolved)

    return VARIABLE_PATTERN.sub(replace, text)


def _resolve_variable(variables: dict[str, Any], name: str) -> Any:
    current: Any = variables
    for part in name.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


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


def _build_files(files: list[Any]) -> list[tuple[str, tuple[str, bytes, str]]]:
    built: list[tuple[str, tuple[str, bytes, str]]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("fieldName") or item.get("field") or "file")
        filename = str(item.get("filename") or "upload.bin")
        content_type = str(item.get("contentType") or "application/octet-stream")
        encoded = str(item.get("base64") or "")
        data = base64.b64decode(encoded) if encoded else b""
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("单个上传文件超过 5MB。")
        built.append((field_name, (filename, data, content_type)))
    return built


def _safe_file_summary(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    return {
        "fieldName": item.get("fieldName") or item.get("field") or "file",
        "filename": item.get("filename") or "upload.bin",
        "contentType": item.get("contentType") or "application/octet-stream",
        "hasBase64": bool(item.get("base64")),
    }


def _parse_form_text(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in value.splitlines():
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        result[key.strip()] = raw_value.strip()
    return result


def _load_metrics(
    durations: list[int],
    repeat: int,
    concurrency: int,
    total_duration_ms: int,
    passed_count: int,
    failed_count: int,
) -> dict[str, Any]:
    sorted_values = sorted(durations)
    return {
        "repeat": repeat,
        "concurrency": concurrency,
        "totalDurationMs": total_duration_ms,
        "passedCount": passed_count,
        "failedCount": failed_count,
        "minMs": min(sorted_values) if sorted_values else 0,
        "maxMs": max(sorted_values) if sorted_values else 0,
        "avgMs": round(statistics.mean(sorted_values), 2) if sorted_values else 0,
        "p50Ms": _percentile(sorted_values, 50),
        "p95Ms": _percentile(sorted_values, 95),
    }


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    position = max(0, min(len(values) - 1, round((percentile / 100) * (len(values) - 1))))
    return values[position]


def _summarize_assertions(assertions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "assertionCount": len(assertions),
        "passedAssertions": sum(1 for item in assertions if item.get("passed")),
        "failedAssertions": sum(1 for item in assertions if not item.get("passed")),
        "categories": _category_counts(assertions),
    }


def _category_counts(assertions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in assertions:
        key = str(item.get("category") or "custom")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _suite_report(step_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "stepIndex": item.get("stepIndex"),
            "name": item.get("name"),
            "passed": item.get("passed"),
            "statusCode": item.get("response", {}).get("statusCode"),
            "durationMs": item.get("response", {}).get("durationMs"),
            "summary": item.get("summary"),
        }
        for item in step_results
    ]


def _assertion(
    name: str,
    passed: bool,
    message: str,
    *,
    category: str,
    actual: Any = None,
    expected: Any = None,
    operator: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "message": message,
        "category": category,
        "actual": actual,
        "expected": expected,
        "operator": operator,
    }


def _get_header(headers: dict[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _try_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _preview(value: str) -> str:
    if len(value) <= MAX_RESPONSE_PREVIEW_CHARS:
        return value
    return value[:MAX_RESPONSE_PREVIEW_CHARS] + "\n...响应内容已截断"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float:
    if value is None:
        raise ValueError("实际值为空，无法进行数值比较")
    return float(value)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__.lower()


def _stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return _json_dumps(value)
    if value is None:
        return ""
    return str(value)


def _compact_value(value: Any, limit: int = 220) -> str:
    text = _stringify(value)
    return text if len(text) <= limit else text[:limit] + "..."


def _make_run_id(prefix: str) -> str:
    return f"{prefix}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
