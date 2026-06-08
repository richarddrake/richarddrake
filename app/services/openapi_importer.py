from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.services.case_quality import build_coverage_report, enrich_case_dict


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


async def generate_cases_from_openapi(
    *,
    content: str = "",
    url: str = "",
    base_url: str = "",
) -> dict[str, Any]:
    document_text = content.strip()
    source = "pasted-openapi"
    if url.strip():
        source = url.strip()
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(source)
            response.raise_for_status()
            document_text = response.text
    if not document_text:
        raise ValueError("请提供 OpenAPI/Swagger JSON/YAML 内容或文档 URL。")

    spec = _parse_document(document_text)
    resolved_base_url = _resolve_base_url(spec, base_url)
    operations = _collect_operations(spec)
    cases: list[dict[str, Any]] = []

    for operation in operations:
        cases.extend(_cases_for_operation(operation, spec, resolved_base_url, source, len(cases)))

    enriched = [enrich_case_dict(case, cases) for case in cases]
    return {
        "source": source,
        "title": spec.get("info", {}).get("title", "OpenAPI"),
        "version": spec.get("info", {}).get("version", ""),
        "baseUrl": resolved_base_url,
        "operationCount": len(operations),
        "caseCount": len(enriched),
        "operations": [
            {
                "method": item["method"],
                "path": item["path"],
                "operationId": item.get("operationId", ""),
                "summary": item.get("summary", ""),
            }
            for item in operations
        ],
        "cases": enriched,
        "coverageReport": build_coverage_report(enriched),
    }


def _parse_document(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:
            raise ValueError("当前环境缺少 PyYAML，无法解析 YAML OpenAPI 文件。") from exc
        value = yaml.safe_load(text)
    if not isinstance(value, dict):
        raise ValueError("OpenAPI 文档必须解析为对象。")
    if "paths" not in value or not isinstance(value["paths"], dict):
        raise ValueError("OpenAPI 文档缺少 paths。")
    return value


def _resolve_base_url(spec: dict[str, Any], base_url: str) -> str:
    if base_url.strip():
        return base_url.strip().rstrip("/")
    servers = spec.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict) and first.get("url"):
            return str(first["url"]).rstrip("/")
    host = spec.get("host")
    if host:
        scheme = "https"
        schemes = spec.get("schemes")
        if isinstance(schemes, list) and schemes:
            scheme = str(schemes[0])
        base_path = str(spec.get("basePath") or "").rstrip("/")
        return f"{scheme}://{host}{base_path}".rstrip("/")
    return "{{base_url}}"


def _collect_operations(spec: dict[str, Any]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for path, path_item in (spec.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        path_params = path_item.get("parameters") if isinstance(path_item.get("parameters"), list) else []
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            merged = dict(operation)
            merged["path"] = path
            merged["method"] = method.upper()
            merged["parameters"] = [*path_params, *(operation.get("parameters") or [])]
            operations.append(merged)
    return operations


def _cases_for_operation(
    operation: dict[str, Any],
    spec: dict[str, Any],
    base_url: str,
    source: str,
    start_index: int,
) -> list[dict[str, Any]]:
    method = operation["method"]
    path = operation["path"]
    summary = operation.get("summary") or operation.get("operationId") or f"{method} {path}"
    tags = operation.get("tags") if isinstance(operation.get("tags"), list) else []
    parameters = [_resolve_ref(item, spec) for item in operation.get("parameters") or []]
    request_schema = _request_body_schema(operation, spec)
    response_status, response_schema = _response_schema(operation, spec)
    positive_payload = _api_payload(
        method=method,
        url=_build_url(base_url, path, parameters),
        operation=operation,
        parameters=parameters,
        body_schema=request_schema,
        response_status=response_status,
        response_schema=response_schema,
    )

    cases = [
        _case(
            index=start_index + 1,
            operation=operation,
            title=f"{summary} 正向请求成功",
            case_type="接口",
            priority="P0",
            scenario="覆盖接口主流程和响应结构契约。",
            steps=["准备合法请求参数和请求体", f"发送 {method} {path}", "校验状态码、响应结构和关键字段"],
            expected=["返回期望状态码", "响应体符合 OpenAPI Schema", "关键字段类型正确"],
            tags=[*tags, "接口", "主流程", "正向"],
            source=source,
            api_test=positive_payload,
        )
    ]

    required_params = [item for item in parameters if item.get("required")]
    for param in required_params[:3]:
        cases.append(
            _case(
                index=start_index + len(cases) + 1,
                operation=operation,
                title=f"{summary} 缺少必填参数 {param.get('name')}",
                case_type="异常",
                priority="P0",
                scenario="覆盖必填参数缺失时的服务端校验。",
                steps=[f"移除必填参数 {param.get('name')}", f"发送 {method} {path}", "检查错误响应"],
                expected=["请求被拒绝", "返回 400/422 类参数错误", "错误信息能定位缺失字段"],
                tags=[*tags, "接口", "字段", "异常"],
                source=source,
                api_test=_api_payload(
                    method=method,
                    url=_build_url(base_url, path, parameters, omit_param=param.get("name")),
                    operation=operation,
                    parameters=parameters,
                    body_schema=request_schema,
                    response_status=400,
                    response_schema=None,
                    omit_param=str(param.get("name") or ""),
                ),
            )
        )

    invalid_param = _first_typed_parameter(parameters)
    if invalid_param:
        cases.append(
            _case(
                index=start_index + len(cases) + 1,
                operation=operation,
                title=f"{summary} 参数 {invalid_param.get('name')} 类型非法",
                case_type="异常",
                priority="P1",
                scenario="覆盖参数类型与格式非法时的接口校验。",
                steps=[f"把 {invalid_param.get('name')} 设置为非法类型", f"发送 {method} {path}", "检查参数错误响应"],
                expected=["请求被拒绝", "错误信息包含非法字段或格式原因"],
                tags=[*tags, "接口", "字段", "异常"],
                source=source,
                api_test=_api_payload(
                    method=method,
                    url=_build_url(base_url, path, parameters),
                    operation=operation,
                    parameters=parameters,
                    body_schema=request_schema,
                    response_status=400,
                    response_schema=None,
                    invalid_param=str(invalid_param.get("name") or ""),
                ),
            )
        )

    boundary = _boundary_parameter(parameters) or _boundary_body_field(request_schema)
    if boundary:
        cases.append(
            _case(
                index=start_index + len(cases) + 1,
                operation=operation,
                title=f"{summary} 边界值 {boundary}",
                case_type="边界",
                priority="P1",
                scenario="覆盖字段边界、长度或数值范围。",
                steps=[f"构造边界值字段 {boundary}", f"发送 {method} {path}", "校验边界处理结果"],
                expected=["合法边界可通过", "非法边界被明确拒绝", "错误信息包含限制说明"],
                tags=[*tags, "接口", "边界", "字段"],
                source=source,
                api_test=positive_payload,
            )
        )

    if operation.get("security") or spec.get("security"):
        auth_payload = dict(positive_payload)
        auth_payload["headers"] = {key: value for key, value in (auth_payload.get("headers") or {}).items() if key.lower() != "authorization"}
        auth_payload["expectedStatus"] = 401
        cases.append(
            _case(
                index=start_index + len(cases) + 1,
                operation=operation,
                title=f"{summary} 未授权访问被拒绝",
                case_type="安全",
                priority="P0",
                scenario="覆盖鉴权缺失或无权限访问。",
                steps=["移除 Authorization 或登录态", f"发送 {method} {path}", "检查权限拦截响应"],
                expected=["返回 401/403", "不泄露敏感数据", "不会产生业务数据变更"],
                tags=[*tags, "接口", "权限", "安全"],
                source=source,
                api_test=auth_payload,
            )
        )

    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        repeat_payload = dict(positive_payload)
        repeat_payload["name"] = f"{summary} 重复提交"
        cases.append(
            _case(
                index=start_index + len(cases) + 1,
                operation=operation,
                title=f"{summary} 重复请求幂等性",
                case_type="稳定性",
                priority="P1",
                scenario="覆盖重复提交、幂等控制和脏数据风险。",
                steps=["使用同一请求连续调用两次", "比较两次响应与业务状态", "检查是否产生重复记录"],
                expected=["重复请求被幂等处理或明确拒绝", "不会产生重复业务记录", "响应语义稳定"],
                tags=[*tags, "接口", "幂等", "并发"],
                source=source,
                api_test=repeat_payload,
            )
        )

    return cases


def _case(
    *,
    index: int,
    operation: dict[str, Any],
    title: str,
    case_type: str,
    priority: str,
    scenario: str,
    steps: list[str],
    expected: list[str],
    tags: list[str],
    source: str,
    api_test: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": f"API-{index:03d}",
        "module": operation.get("operationId") or f"{operation.get('method')} {operation.get('path')}",
        "title": title,
        "priority": priority,
        "case_type": case_type,
        "scenario": scenario,
        "preconditions": ["已确认接口基础地址、鉴权方式和测试环境可用"],
        "steps": steps,
        "expected_results": expected,
        "test_data": _json_dumps(api_test.get("body") or api_test.get("variables") or {}),
        "tags": tags,
        "source": source,
        "requirement_id": operation.get("operationId") or "",
        "source_type": "openapi",
        "api_test": api_test,
    }


def _api_payload(
    *,
    method: str,
    url: str,
    operation: dict[str, Any],
    parameters: list[dict[str, Any]],
    body_schema: dict[str, Any] | None,
    response_status: int,
    response_schema: dict[str, Any] | None,
    omit_param: str = "",
    invalid_param: str = "",
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    body = ""
    body_mode = "raw"
    if body_schema:
        headers["Content-Type"] = "application/json"
        body_mode = "json"
        body_value = _sample_from_schema(body_schema)
        if omit_param and isinstance(body_value, dict):
            body_value.pop(omit_param, None)
        if invalid_param and isinstance(body_value, dict) and invalid_param in body_value:
            body_value[invalid_param] = "__invalid__"
        body = _json_dumps(body_value)

    assertions = [{"name": "HTTP 状态码", "source": "status", "operator": "equals", "expected": response_status}]
    if response_schema:
        assertions.append({"name": "响应 JSON 存在", "source": "json", "path": "$", "operator": "exists"})

    return {
        "name": operation.get("summary") or operation.get("operationId") or f"{method} {operation.get('path')}",
        "method": method,
        "url": url,
        "headers": headers,
        "body": body,
        "bodyMode": body_mode,
        "expectedStatus": response_status,
        "expectedContains": "",
        "timeoutSeconds": 10,
        "maxResponseMs": 3000,
        "variables": _variables_from_url(url)
        | _variables_from_parameters(parameters, omit_param=omit_param, invalid_param=invalid_param),
        "assertions": assertions,
        "extractors": [],
        "databaseAssertions": [],
        "jsonSchema": response_schema,
    }


def _build_url(base_url: str, path: str, parameters: list[dict[str, Any]], omit_param: str = "") -> str:
    rendered_path = path
    query_parts = []
    for param in parameters:
        name = str(param.get("name") or "")
        if not name or name == omit_param:
            continue
        location = param.get("in")
        value = _sample_from_schema(_param_schema(param))
        if location == "path":
            rendered_path = rendered_path.replace("{" + name + "}", str(value))
        elif location == "query":
            query_parts.append(f"{name}={value}")
    url = f"{base_url.rstrip('/')}/{rendered_path.lstrip('/')}"
    if query_parts:
        url += "?" + "&".join(query_parts)
    return url


def _variables_from_parameters(parameters: list[dict[str, Any]], omit_param: str = "", invalid_param: str = "") -> dict[str, Any]:
    variables: dict[str, Any] = {}
    for param in parameters:
        name = str(param.get("name") or "")
        if not name or name == omit_param:
            continue
        value = _sample_from_schema(_param_schema(param))
        if name == invalid_param:
            value = "__invalid__"
        variables[name] = value
    return variables


def _variables_from_url(url: str) -> dict[str, Any]:
    if "{{base_url}}" in url:
        return {"base_url": "http://127.0.0.1:8000"}
    return {}


def _request_body_schema(operation: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any] | None:
    request_body = _resolve_ref(operation.get("requestBody"), spec)
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content") or {}
    for media_type in ["application/json", "application/*+json"]:
        media = content.get(media_type)
        if isinstance(media, dict) and media.get("schema"):
            return _resolve_ref(media["schema"], spec)
    for media in content.values():
        if isinstance(media, dict) and media.get("schema"):
            return _resolve_ref(media["schema"], spec)
    return None


def _response_schema(operation: dict[str, Any], spec: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
    responses = operation.get("responses") or {}
    selected_status = "200"
    for status in responses:
        if str(status).startswith("2"):
            selected_status = str(status)
            break
    response = _resolve_ref(responses.get(selected_status) or {}, spec)
    content = response.get("content") if isinstance(response, dict) else {}
    if isinstance(content, dict):
        for media in content.values():
            if isinstance(media, dict) and media.get("schema"):
                return _status_to_int(selected_status), _resolve_ref(media["schema"], spec)
    return _status_to_int(selected_status), None


def _first_typed_parameter(parameters: list[dict[str, Any]]) -> dict[str, Any] | None:
    for param in parameters:
        schema = _param_schema(param)
        if schema.get("type") in {"integer", "number", "boolean", "string"}:
            return param
    return None


def _boundary_parameter(parameters: list[dict[str, Any]]) -> str:
    for param in parameters:
        schema = _param_schema(param)
        if any(key in schema for key in ["minimum", "maximum", "minLength", "maxLength"]):
            return str(param.get("name") or "")
    return ""


def _boundary_body_field(schema: dict[str, Any] | None) -> str:
    if not isinstance(schema, dict):
        return ""
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        return ""
    for name, child in properties.items():
        if isinstance(child, dict) and any(key in child for key in ["minimum", "maximum", "minLength", "maxLength"]):
            return str(name)
    return ""


def _param_schema(param: dict[str, Any]) -> dict[str, Any]:
    schema = param.get("schema")
    if isinstance(schema, dict):
        return schema
    if param.get("type"):
        return {"type": param.get("type"), "format": param.get("format")}
    return {"type": "string"}


def _sample_from_schema(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return "sample"
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]
    schema_type = schema.get("type")
    if not schema_type and "properties" in schema:
        schema_type = "object"
    if schema_type == "object":
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        result = {}
        for name, child_schema in properties.items():
            if name in required or len(result) < 8:
                result[name] = _sample_from_schema(child_schema)
        return result
    if schema_type == "array":
        return [_sample_from_schema(schema.get("items") or {"type": "string"})]
    if schema_type == "integer":
        return int(schema.get("minimum") or 1)
    if schema_type == "number":
        return float(schema.get("minimum") or 1.0)
    if schema_type == "boolean":
        return True
    if schema.get("format") == "date-time":
        return "2026-06-08T00:00:00Z"
    if schema.get("format") == "date":
        return "2026-06-08"
    if schema.get("format") == "email":
        return "qa@example.com"
    min_length = schema.get("minLength")
    if isinstance(min_length, int) and min_length > 1:
        return "x" * min(min_length, 24)
    return "sample"


def _resolve_ref(value: Any, spec: dict[str, Any]) -> Any:
    if isinstance(value, dict) and "$ref" in value:
        ref = str(value["$ref"])
        if ref.startswith("#/"):
            current: Any = spec
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return value
            return _resolve_ref(current, spec)
    if isinstance(value, dict):
        return {key: _resolve_ref(item, spec) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_ref(item, spec) for item in value]
    return value


def _status_to_int(status: str) -> int:
    match = re.search(r"\d{3}", str(status))
    return int(match.group(0)) if match else 200


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
