from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any


COMMON_QUERY_PARAMS = {"application", "application_client_type", "token", "ajax"}


@dataclass
class ApiParamFact:
    name: str
    type: str = ""
    required: bool = False
    default: str = ""
    description: str = ""


@dataclass
class ApiDocFact:
    title: str
    method: str
    path: str
    source_url: str = ""
    description: str = ""
    request_sample: dict[str, Any] | None = None
    request_params: list[ApiParamFact] | None = None
    response_fields: list[str] | None = None
    response_sample: dict[str, Any] | None = None
    content: str = ""

    @property
    def param_names(self) -> list[str]:
        names: list[str] = []
        for param in self.request_params or []:
            if param.name and param.name not in names:
                names.append(param.name)
        for name in (self.request_sample or {}).keys():
            if name and name not in names:
                names.append(str(name))
        return names

    @property
    def business_param_names(self) -> list[str]:
        return [name for name in self.param_names if name not in COMMON_QUERY_PARAMS]


def extract_api_doc_facts(material_context: str) -> list[ApiDocFact]:
    if "请求URL" not in material_context or "请求方式" not in material_context:
        return []

    lines = [_clean_doc_cell(line) for line in material_context.splitlines()]
    facts: list[ApiDocFact] = []
    seen: set[tuple[str, str]] = set()
    for index, line in enumerate(lines):
        if line != "请求URL":
            continue
        path = _next_doc_value(lines, index)
        method_index = _find_next_line(lines, "请求方式", index + 1, index + 20)
        method = _next_doc_value(lines, method_index).upper() if method_index >= 0 else ""
        if not path or not method or not re.match(r"^[A-Z]+$", method):
            continue
        key = (method, path)
        if key in seen:
            continue
        seen.add(key)

        start = max(0, index - 90)
        end = min(len(lines), index + 220)
        chunk = "\n".join(lines[start:end])
        title = _nearest_doc_title(lines, index) or path
        if " - " in title:
            title = title.split(" - ", 1)[0].strip()
        description_index = _find_previous_line(lines, "简要描述", index, index - 40)
        description = _next_doc_value(lines, description_index) if description_index >= 0 else title
        request_sample = _extract_request_sample(chunk)
        request_params = _extract_request_param_facts(chunk, request_sample)
        response_sample = _extract_response_sample(chunk)
        response_fields = _flatten_response_fields(response_sample)
        facts.append(
            ApiDocFact(
                title=title or description or path,
                method=method,
                path=path,
                source_url=_nearest_source_url(lines, index),
                description=description,
                request_sample=request_sample,
                request_params=request_params,
                response_fields=response_fields,
                response_sample=response_sample,
                content=chunk,
            )
        )
    return facts


def select_api_doc_facts(
    facts: list[ApiDocFact],
    requirements: str,
    context: str,
    limit: int = 3,
) -> list[ApiDocFact]:
    focus = f"{requirements}\n{context}".strip()
    ranked = sorted(facts, key=lambda item: _fact_score(item, focus), reverse=True)
    return ranked[:limit]


def build_api_doc_cases(requirements: str, context: str, material_context: str) -> list[dict[str, Any]]:
    facts = select_api_doc_facts(extract_api_doc_facts(material_context), requirements, context)
    cases: list[dict[str, Any]] = []
    for fact in facts:
        cases.extend(_fact_cases(fact))
    return cases[:18]


def facts_to_prompt_context(facts: list[ApiDocFact], limit: int = 3) -> str:
    selected = facts[:limit]
    payload = []
    for fact in selected:
        payload.append(
            {
                "title": fact.title,
                "method": fact.method,
                "path": fact.path,
                "source_url": fact.source_url,
                "description": fact.description,
                "request_sample": fact.request_sample or {},
                "request_params": [
                    {
                        "name": param.name,
                        "type": param.type,
                        "required": param.required,
                        "default": param.default,
                        "description": param.description,
                    }
                    for param in fact.request_params or []
                ],
                "response_fields": fact.response_fields or [],
                "response_sample": fact.response_sample or {},
            }
        )
    fact_json = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"""
接口文档事实强约束：
{fact_json}

生成要求：
1. 必须基于上面的真实接口事实扩展测试场景，不要改写请求方法和接口路径。
2. 每条接口自动化用例必须携带 api_test。
3. api_test.method 必须等于接口事实中的 method。
4. api_test.url 必须包含真实接口路径，例如 /api.php?s=buy/index 或同等 query path。
5. 不要使用平台自测接口，例如 /api/database/status、/api/history、/api/api-tests/run。
6. 正向用例优先使用 request_sample；异常、权限、幂等、契约、边界场景可以在 request_sample 基础上变形。
7. 断言必须至少覆盖 HTTP 状态码和响应 JSON 中的 code/msg/data 或文档响应字段。
""".strip()


def describe_api_doc_facts(facts: list[ApiDocFact], limit: int = 3) -> str:
    parts = []
    for fact in facts[:limit]:
        params = ", ".join(fact.business_param_names[:8]) or "无显式业务参数"
        fields = ", ".join((fact.response_fields or [])[:8]) or "未提取到响应字段"
        parts.append(f"{fact.method} {fact.path}（参数：{params}；响应：{fields}）")
    suffix = f"；另有 {len(facts) - limit} 个接口未展示" if len(facts) > limit else ""
    return f"已识别接口事实：{'；'.join(parts)}{suffix}。"


def _fact_cases(fact: ApiDocFact) -> list[dict[str, Any]]:
    module = fact.title or fact.path
    source = f"网页接口文档：{fact.source_url or fact.path}"
    business_params = fact.business_param_names
    primary_param = _pick_primary_param(business_params, fact.request_sample or {})
    sample_payload = fact.request_sample or _sample_payload_from_params(business_params)
    invalid_payload = dict(sample_payload)
    if primary_param:
        invalid_payload[primary_param] = "invalid"
    missing_payload = dict(sample_payload)
    if primary_param:
        missing_payload.pop(primary_param, None)

    return [
        _api_doc_case(
            fact,
            title=f"{module}接口正向请求成功",
            priority="P0",
            case_type="接口",
            scenario=f"使用文档示例参数调用 {fact.method} {fact.path}",
            preconditions=["ShopXO API 服务已启动", "已准备有效业务数据", "如接口需要登录则已准备有效 token"],
            steps=["设置 base_url、application、application_client_type 和 token 变量", "按文档示例参数发送请求", "校验响应状态码和业务 code"],
            expected_results=["HTTP 状态码为 200", "响应 JSON 中 code 为 0", "返回 msg 字段和业务 data 字段"],
            test_data=sample_payload,
            tags=["接口", "正向", "网页文档"],
            source=source,
            body=sample_payload,
            assertions=_positive_assertions(),
            expected_contains="code",
        ),
        _api_doc_case(
            fact,
            title=f"{module}接口缺少关键参数时返回失败",
            priority="P0",
            case_type="异常",
            scenario=f"覆盖 {primary_param or '关键业务参数'} 缺失后的参数校验",
            preconditions=["ShopXO API 服务已启动", "接口文档已声明请求参数"],
            steps=[f"移除请求参数 {primary_param or '关键字段'}", "发送接口请求", "校验失败响应"],
            expected_results=["HTTP 状态码为 200 或接口约定错误状态", "响应 JSON 中 code 不为 0", "错误提示能够说明参数缺失或请求失败"],
            test_data=missing_payload,
            tags=["接口", "缺参", "异常"],
            source=source,
            body=missing_payload,
            assertions=_negative_assertions(),
            expected_contains="code",
        ),
        _api_doc_case(
            fact,
            title=f"{module}接口参数类型非法时返回失败",
            priority="P1",
            case_type="异常",
            scenario=f"覆盖 {primary_param or '业务参数'} 类型非法或格式错误",
            preconditions=["ShopXO API 服务已启动"],
            steps=[f"将 {primary_param or '业务参数'} 设置为非法字符串", "发送接口请求", "校验接口未按成功处理"],
            expected_results=["HTTP 状态码为 200 或接口约定错误状态", "响应 JSON 中 code 不为 0", "不会产生成功业务数据"],
            test_data=invalid_payload,
            tags=["接口", "非法参数"],
            source=source,
            body=invalid_payload,
            assertions=_negative_assertions(),
            expected_contains="code",
        ),
        _api_doc_case(
            fact,
            title=f"{module}接口无效 token 场景校验",
            priority="P0",
            case_type="权限",
            scenario="覆盖登录态缺失、token 过期或 token 非法",
            preconditions=["ShopXO API 服务已启动", "接口存在用户态或订单态数据"],
            steps=["将 token 变量设置为空或无效值", "发送接口请求", "校验鉴权失败或业务拒绝"],
            expected_results=["接口不应按已登录用户成功处理", "响应 JSON 中 code 不为 0 或返回明确鉴权提示"],
            test_data=sample_payload,
            tags=["接口", "权限", "token"],
            source=source,
            body=sample_payload,
            variables={"token": "invalid-token"},
            assertions=_negative_assertions(),
            expected_contains="code",
        ),
        _api_doc_case(
            fact,
            title=f"{module}接口重复提交幂等性校验",
            priority="P1",
            case_type="幂等",
            scenario="覆盖短时间重复调用同一业务请求",
            preconditions=["ShopXO API 服务已启动", "准备一组可重复验证的业务数据"],
            steps=["使用相同参数连续发送两次请求", "分别记录两次响应", "核对业务状态是否重复变更"],
            expected_results=["接口不产生重复扣减、重复支付或重复业务记录", "第二次请求返回明确状态或保持幂等结果"],
            test_data=sample_payload,
            tags=["接口", "重复提交", "数据一致性"],
            source=source,
            body=sample_payload,
            assertions=[
                {"name": "HTTP 状态码为 200", "source": "status", "operator": "equals", "expected": 200},
                {"name": "响应业务码存在", "source": "json", "path": "$.code", "operator": "exists"},
            ],
            expected_contains="code",
        ),
        _api_doc_case(
            fact,
            title=f"{module}接口响应契约字段校验",
            priority="P1",
            case_type="契约",
            scenario="覆盖文档返回示例中的基础字段结构",
            preconditions=["ShopXO API 服务已启动"],
            steps=["按文档示例参数发送请求", "检查响应 JSON 结构", "校验 code、msg、data 字段存在"],
            expected_results=["响应为 JSON 对象", "code、msg、data 字段存在", "字段类型与接口文档示例一致"],
            test_data=sample_payload,
            tags=["接口", "响应契约", "JSON"],
            source=source,
            body=sample_payload,
            assertions=_contract_assertions(fact),
            expected_contains="code",
            json_schema=_json_schema_for_fact(fact),
        ),
    ]


def _api_doc_case(
    fact: ApiDocFact,
    *,
    title: str,
    priority: str,
    case_type: str,
    scenario: str,
    preconditions: list[str],
    steps: list[str],
    expected_results: list[str],
    test_data: dict[str, Any],
    tags: list[str],
    source: str,
    body: dict[str, Any],
    assertions: list[dict[str, Any]],
    expected_contains: str,
    variables: dict[str, str] | None = None,
    json_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "module": fact.title or fact.path,
        "title": title,
        "priority": priority,
        "case_type": case_type,
        "scenario": scenario,
        "preconditions": preconditions,
        "steps": steps,
        "expected_results": expected_results,
        "test_data": json.dumps(test_data, ensure_ascii=False),
        "tags": tags,
        "source": source,
        "requirement_id": fact.path,
        "api_test": _api_test_for_fact(fact, body, assertions, expected_contains, variables, json_schema),
    }


def _api_test_for_fact(
    fact: ApiDocFact,
    body: dict[str, Any],
    assertions: list[dict[str, Any]],
    expected_contains: str,
    variables: dict[str, str] | None,
    json_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    common_variables = {
        "base_url": os.getenv("API_DOC_DEFAULT_BASE_URL", "http://127.0.0.1:8080"),
        "application": "app",
        "application_client_type": "weixin",
        "token": "",
        **(variables or {}),
    }
    query = "application={{application}}&application_client_type={{application_client_type}}&token={{token}}&ajax=ajax"
    return {
        "name": f"{fact.title or fact.path} - {fact.method} {fact.path}",
        "method": fact.method,
        "url": f"{{{{base_url}}}}/api.php?s={fact.path}&{query}",
        "headers": {"Accept": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
        "bodyMode": "form" if fact.method in {"POST", "PUT", "PATCH"} else "raw",
        "formFields": body if fact.method in {"POST", "PUT", "PATCH"} else {},
        "expectedStatus": 200,
        "expectedContains": expected_contains,
        "timeoutSeconds": 10,
        "maxResponseMs": 3000,
        "variables": common_variables,
        "assertions": assertions,
        "extractors": [],
        "databaseAssertions": [],
        "jsonSchema": json_schema,
    }


def _positive_assertions() -> list[dict[str, Any]]:
    return [
        {"name": "HTTP 状态码为 200", "source": "status", "operator": "equals", "expected": 200},
        {"name": "业务 code 为 0", "source": "json", "path": "$.code", "operator": "equals", "expected": 0},
        {"name": "msg 字段存在", "source": "json", "path": "$.msg", "operator": "exists"},
    ]


def _negative_assertions() -> list[dict[str, Any]]:
    return [
        {"name": "HTTP 状态码为 200", "source": "status", "operator": "equals", "expected": 200},
        {"name": "业务 code 不为 0", "source": "json", "path": "$.code", "operator": "not_equals", "expected": 0},
        {"name": "msg 字段存在", "source": "json", "path": "$.msg", "operator": "exists"},
    ]


def _contract_assertions(fact: ApiDocFact) -> list[dict[str, Any]]:
    fields = fact.response_fields or ["code", "msg", "data"]
    assertions = [{"name": "HTTP 状态码为 200", "source": "status", "operator": "equals", "expected": 200}]
    for field in fields[:8]:
        root = field.split(".", 1)[0]
        if root:
            assertions.append({"name": f"{root} 字段存在", "source": "json", "path": f"$.{root}", "operator": "exists"})
    return assertions


def _json_schema_for_fact(fact: ApiDocFact) -> dict[str, Any]:
    required = [field for field in ["code", "msg", "data"] if field in (fact.response_fields or [])]
    if not required:
        required = ["code", "msg", "data"]
    return {
        "type": "object",
        "required": required,
        "properties": {
            "code": {"type": ["integer", "number", "string"]},
            "msg": {"type": "string"},
            "data": {"type": ["object", "array", "string", "null"]},
        },
    }


def _extract_request_sample(chunk: str) -> dict[str, Any]:
    sample_area = chunk
    if "请求参数" in chunk:
        sample_area = chunk.split("请求参数", 1)[1].split("参数名", 1)[0]
    for item in _json_objects(sample_area):
        if isinstance(item, dict):
            return item
    return {}


def _extract_response_sample(chunk: str) -> dict[str, Any]:
    if "返回示例" not in chunk:
        return {}
    area = chunk.split("返回示例", 1)[1]
    candidates = [item for item in _json_objects(area) if isinstance(item, dict)]
    if not candidates:
        return {}
    candidates.sort(key=lambda item: ({"code", "msg", "data"}.issubset(item.keys()), len(json.dumps(item, ensure_ascii=False))), reverse=True)
    return candidates[0]


def _extract_request_param_facts(chunk: str, sample: dict[str, Any]) -> list[ApiParamFact]:
    params: list[ApiParamFact] = [ApiParamFact(name=str(name), type=_guess_type(value)) for name, value in sample.items()]
    known = {param.name for param in params}
    if "请求参数" not in chunk:
        return params

    area = chunk.split("请求参数", 1)[1].split("返回示例", 1)[0]
    for line in area.splitlines():
        cells = [_clean_doc_cell(item) for item in line.split("|")]
        cells = [cell for cell in cells if cell]
        if len(cells) < 2:
            continue
        name = cells[0]
        if name in {"参数名", "是否必须", "类型", "默认值", "描述"}:
            continue
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name) or name in known:
            continue
        required = cells[1] if len(cells) > 1 else ""
        param_type = cells[2] if len(cells) > 2 else ""
        if len(cells) >= 5:
            default = cells[3]
            description = cells[4]
        else:
            default = ""
            description = cells[3] if len(cells) > 3 else ""
        params.append(
            ApiParamFact(
                name=name,
                type=param_type,
                required=required in {"是", "必填", "true", "True", "1"},
                default=default,
                description=description,
            )
        )
        known.add(name)
    return params


def _json_objects(text: str) -> list[Any]:
    results: list[Any] = []
    start = -1
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start >= 0:
                snippet = text[start : index + 1]
                try:
                    results.append(json.loads(snippet))
                except json.JSONDecodeError:
                    pass
                start = -1
    return results


def _flatten_response_fields(value: Any, prefix: str = "", limit: int = 30) -> list[str]:
    fields: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            fields.append(name)
            if len(fields) >= limit:
                return fields[:limit]
            fields.extend(_flatten_response_fields(child, name, limit - len(fields)))
            if len(fields) >= limit:
                return fields[:limit]
    elif isinstance(value, list) and value:
        fields.extend(_flatten_response_fields(value[0], f"{prefix}[]" if prefix else "[]", limit))
    return fields[:limit]


def _sample_payload_from_params(params: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for param in params:
        lower = param.lower()
        if lower.endswith("_id") or lower == "id" or lower == "ids":
            payload[param] = "1"
        elif "stock" in lower or "num" in lower or "count" in lower:
            payload[param] = "1"
        else:
            payload[param] = "test"
    return payload


def _pick_primary_param(params: list[str], sample: dict[str, Any]) -> str:
    for candidate in ("ids", "id", "order_id", "goods_id", "payment_id"):
        if candidate in sample or candidate in params:
            return candidate
    return params[0] if params else next(iter(sample), "")


def _guess_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _fact_score(fact: ApiDocFact, focus: str) -> int:
    text = f"{fact.title} {fact.description} {fact.path} {fact.content}".lower()
    terms = set(re.findall(r"[A-Za-z0-9_/-]{3,}", focus.lower()))
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", focus.lower()):
        terms.add(phrase)
        for size in (2, 3, 4):
            for index in range(0, max(0, len(phrase) - size + 1)):
                terms.add(phrase[index : index + size])
    return sum(1 for term in terms if term and term in text)


def _clean_doc_cell(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _next_doc_value(lines: list[str], index: int) -> str:
    if index < 0:
        return ""
    for line in lines[index + 1 : index + 8]:
        value = _clean_doc_cell(line)
        if value:
            return value
    return ""


def _find_next_line(lines: list[str], target: str, start: int, end: int) -> int:
    end = min(len(lines), end)
    for index in range(max(0, start), end):
        if lines[index] == target:
            return index
    return -1


def _find_previous_line(lines: list[str], target: str, start: int, end: int) -> int:
    for index in range(min(start, len(lines) - 1), max(-1, end), -1):
        if lines[index] == target:
            return index
    return -1


def _nearest_doc_title(lines: list[str], index: int) -> str:
    for cursor in range(index, max(-1, index - 120), -1):
        line = lines[cursor]
        if line.startswith("【网页文档：") and line.endswith("】"):
            return line.removeprefix("【网页文档：").removesuffix("】").strip()
    return ""


def _nearest_source_url(lines: list[str], index: int) -> str:
    for cursor in range(index, max(-1, index - 120), -1):
        line = lines[cursor]
        if line.startswith("来源："):
            return line.removeprefix("来源：").strip()
    return ""
