# 这个模块负责在接口执行失败后给出原因归类、证据摘要和下一步排查建议。
from __future__ import annotations

from typing import Any


def analyze_failure(result: dict[str, Any], case: dict[str, Any] | None = None) -> dict[str, Any]:
    if result.get("passed"):
        return {
            "category": "passed",
            "confidence": 1.0,
            "summary": "执行通过，无需失败分析。",
            "evidence": [],
            "nextSteps": [],
            "caseUpdateSuggestion": "",
        }

    assertions = result.get("assertions") or []
    failed_assertions = [item for item in assertions if not item.get("passed")]
    error = str(result.get("error") or "")
    response = result.get("response") or {}
    status_code = response.get("statusCode")
    request = result.get("request") or {}
    categories = _score_categories(error, status_code, failed_assertions, result)
    category, score = max(categories.items(), key=lambda item: item[1])

    evidence = _evidence(error, status_code, failed_assertions, result)
    next_steps = _next_steps(category, request, case or {})
    summary = _summary(category, status_code, failed_assertions, error)

    return {
        "category": category,
        "confidence": round(min(0.95, max(0.35, score / 10)), 2),
        "summary": summary,
        "evidence": evidence,
        "nextSteps": next_steps,
        "caseUpdateSuggestion": _case_update_suggestion(category),
        "shouldCreateDefect": _should_create_defect(category, score),
        "shouldUpdateCase": category in {"assertion", "api_contract_changed", "request_params", "auth"},
    }


def _score_categories(
    error: str,
    status_code: Any,
    failed_assertions: list[dict[str, Any]],
    result: dict[str, Any],
) -> dict[str, int]:
    scores = {
        "environment": 1,
        "auth": 1,
        "request_params": 1,
        "assertion": 1,
        "api_contract_changed": 1,
        "backend_bug": 1,
        "database_consistency": 1,
    }
    lowered_error = error.lower()

    if "timeout" in lowered_error or "超时" in error or "connect" in lowered_error or "请求失败" in error:
        scores["environment"] += 7
    if status_code in {401, 403}:
        scores["auth"] += 8
    if status_code in {400, 422}:
        scores["request_params"] += 7
    if status_code == 404:
        scores["api_contract_changed"] += 7
    if isinstance(status_code, int) and status_code >= 500:
        scores["backend_bug"] += 8

    for item in failed_assertions:
        category = str(item.get("category") or "").lower()
        message = str(item.get("message") or "")
        name = str(item.get("name") or "")
        if category in {"status", "schema"} or "Schema" in name:
            scores["api_contract_changed"] += 3
        if category in {"body", "json", "header", "custom"}:
            scores["assertion"] += 3
        if category == "database":
            scores["database_consistency"] += 7
        if "缺失" in message or "不存在" in message:
            scores["api_contract_changed"] += 2
        if "期望" in message and "实际" in message:
            scores["assertion"] += 2

    if result.get("databaseChecks"):
        failed_db = [item for item in result.get("databaseChecks") or [] if not item.get("passed")]
        if failed_db:
            scores["database_consistency"] += 6

    return scores


def _evidence(error: str, status_code: Any, failed_assertions: list[dict[str, Any]], result: dict[str, Any]) -> list[str]:
    items: list[str] = []
    if error:
        items.append(f"执行错误：{error}")
    if status_code is not None:
        items.append(f"实际 HTTP 状态码：{status_code}")
    for assertion in failed_assertions[:4]:
        name = assertion.get("name") or "断言"
        message = assertion.get("message") or "未给出断言信息"
        items.append(f"{name} 未通过：{message}")
    response = result.get("response") or {}
    if response.get("bodyPreview"):
        items.append(f"响应摘要：{str(response.get('bodyPreview'))[:240]}")
    return items[:6]


def _next_steps(category: str, request: dict[str, Any], case: dict[str, Any]) -> list[str]:
    url = request.get("url") or case.get("url") or ""
    common = [f"复核请求地址和环境变量：{url}" if url else "复核请求地址和环境变量。"]
    mapping = {
        "environment": common + ["确认后端服务、网络代理、DNS、端口和超时时间。"],
        "auth": ["检查 Authorization、Cookie、Token 有效期和角色权限。", "用有权限账号与无权限账号分别重放请求。"],
        "request_params": ["对照接口文档检查必填参数、类型、枚举和请求体结构。", "保留失败请求样本，和前端实际请求做差异比对。"],
        "assertion": ["确认接口响应是否符合预期，必要时调整断言路径或期望值。", "避免只用响应包含文本，优先改成 JSONPath 或 Schema 断言。"],
        "api_contract_changed": ["对照最新 OpenAPI/Swagger 文档检查 URL、状态码和响应字段是否变更。", "若接口契约已更新，应同步更新测试用例。"],
        "backend_bug": ["查看服务端日志、链路追踪和异常堆栈。", "用同一请求在 Postman/Apifox/curl 中复现。"],
        "database_consistency": ["检查接口执行后的事务提交、数据过滤条件和数据库断言 SQL。", "确认测试数据是否被清理或被其他用例污染。"],
    }
    return mapping.get(category, common)[:4]


def _summary(category: str, status_code: Any, failed_assertions: list[dict[str, Any]], error: str) -> str:
    labels = {
        "environment": "更像是环境、网络或服务可达性问题。",
        "auth": "更像是鉴权、Token 或权限配置问题。",
        "request_params": "更像是请求参数、请求体或必填字段问题。",
        "assertion": "更像是断言设置与实际响应不一致。",
        "api_contract_changed": "更像是接口契约或响应结构发生变化。",
        "backend_bug": "更像是服务端异常或后端缺陷。",
        "database_consistency": "更像是数据库落库或数据一致性问题。",
    }
    detail = labels.get(category, "需要结合日志继续定位。")
    if status_code is not None:
        detail += f" 当前状态码为 {status_code}。"
    if error:
        detail += f" 执行器错误：{error[:120]}"
    elif failed_assertions:
        detail += f" 失败断言数：{len(failed_assertions)}。"
    return detail


def _case_update_suggestion(category: str) -> str:
    if category in {"assertion", "api_contract_changed"}:
        return "建议先确认接口契约是否变更；如果变更属实，应更新用例的断言、Schema 或期望状态码。"
    if category in {"request_params", "auth"}:
        return "建议补充前置条件、环境变量和测试数据说明，让用例可以稳定复现。"
    if category == "database_consistency":
        return "建议把数据库断言和接口返回字段绑定到同一业务编号，减少误判。"
    return "暂不建议直接修改用例，先排查环境和服务端日志。"


def _should_create_defect(category: str, score: int) -> bool:
    if category in {"backend_bug", "database_consistency", "api_contract_changed"}:
        return True
    if category in {"auth", "request_params", "assertion"} and score >= 6:
        return True
    return False
