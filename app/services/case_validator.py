from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.services.api_doc_parser import ApiDocFact, COMMON_QUERY_PARAMS


DEMO_ENDPOINT_MARKERS = (
    "/api/database/status",
    "/api/history",
    "/api/api-tests/run",
    "/api/api-tests/history",
)


@dataclass
class CaseValidationResult:
    passed: bool
    issues: list[str]
    matched_cases: int = 0
    total_api_cases: int = 0


def validate_cases_against_api_facts(
    cases: list[dict[str, Any]],
    facts: list[ApiDocFact],
) -> CaseValidationResult:
    if not facts:
        return CaseValidationResult(passed=True, issues=[])
    if not cases:
        return CaseValidationResult(passed=False, issues=["模型未生成任何测试用例。"])

    issues: list[str] = []
    matched_cases = 0
    api_case_count = 0
    matched_fact_paths: set[str] = set()

    for index, case in enumerate(cases, 1):
        api_test = case.get("api_test")
        if not isinstance(api_test, dict):
            if _looks_like_api_case(case):
                issues.append(f"TC-{index:03d} 是接口场景但缺少 api_test。")
            continue

        api_case_count += 1
        url = str(api_test.get("url") or "")
        method = str(api_test.get("method") or "").upper()
        if any(marker in url for marker in DEMO_ENDPOINT_MARKERS):
            issues.append(f"TC-{index:03d} 使用了平台自测接口 {url}，不是接口文档中的真实接口。")
            continue

        fact = _match_fact(api_test, facts)
        if not fact:
            issues.append(f"TC-{index:03d} 的 api_test 未匹配任何接口事实：{method or 'UNKNOWN'} {url or 'EMPTY_URL'}。")
            continue

        matched_cases += 1
        matched_fact_paths.add(fact.path)
        if method != fact.method:
            issues.append(f"TC-{index:03d} 请求方法应为 {fact.method}，实际为 {method or '空'}。")
        if not _has_meaningful_assertion(api_test, fact):
            issues.append(f"TC-{index:03d} 缺少状态码或响应字段断言。")
        if _is_positive_case(case) and not _uses_sample_payload(api_test, fact):
            issues.append(f"TC-{index:03d} 正向用例未使用接口文档请求示例或业务参数。")

    if api_case_count == 0:
        issues.append("模型结果没有任何可执行 api_test，无法推进到接口执行模块。")

    for fact in facts[:3]:
        if fact.path not in matched_fact_paths:
            issues.append(f"生成结果未覆盖接口事实 {fact.method} {fact.path}。")

    return CaseValidationResult(
        passed=not issues,
        issues=issues,
        matched_cases=matched_cases,
        total_api_cases=api_case_count,
    )


def summarize_validation_issues(result: CaseValidationResult, limit: int = 5) -> str:
    if result.passed:
        return "接口事实校验通过。"
    shown = result.issues[:limit]
    suffix = f"；另有 {len(result.issues) - limit} 个问题" if len(result.issues) > limit else ""
    return "；".join(shown) + suffix


def _match_fact(api_test: dict[str, Any], facts: list[ApiDocFact]) -> ApiDocFact | None:
    url = str(api_test.get("url") or "")
    method = str(api_test.get("method") or "").upper()
    for fact in facts:
        if method and method != fact.method:
            continue
        if _url_contains_fact_path(url, fact.path):
            return fact
    for fact in facts:
        if _url_contains_fact_path(url, fact.path):
            return fact
    return None


def _url_contains_fact_path(url: str, path: str) -> bool:
    normalized_url = url.replace("%2F", "/").replace("%2f", "/")
    if path in normalized_url:
        return True
    return f"s={path}" in normalized_url or f"/{path}" in normalized_url


def _looks_like_api_case(case: dict[str, Any]) -> bool:
    text = " ".join(
        str(case.get(key) or "")
        for key in ("module", "title", "case_type", "scenario", "source", "requirement_id")
    ).lower()
    tags = case.get("tags")
    if isinstance(tags, list):
        text += " " + " ".join(str(tag).lower() for tag in tags)
    return any(keyword in text for keyword in ("接口", "api", "http", "请求", "响应"))


def _is_positive_case(case: dict[str, Any]) -> bool:
    text = " ".join(str(case.get(key) or "") for key in ("title", "case_type", "scenario"))
    tags = case.get("tags")
    if isinstance(tags, list):
        text += " " + " ".join(str(tag) for tag in tags)
    return any(keyword in text for keyword in ("正向", "成功", "主流程", "有效"))


def _has_meaningful_assertion(api_test: dict[str, Any], fact: ApiDocFact) -> bool:
    assertions = api_test.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        return False

    has_status_assertion = False
    has_response_assertion = False
    response_roots = {field.split(".", 1)[0].replace("[]", "") for field in (fact.response_fields or [])}
    response_roots.update({"code", "msg", "data"})
    for assertion in assertions:
        if not isinstance(assertion, dict):
            continue
        source = str(assertion.get("source") or "").lower()
        path = str(assertion.get("path") or "")
        name = str(assertion.get("name") or "")
        if source == "status":
            has_status_assertion = True
        if any(root and (f"$.{root}" in path or root in name) for root in response_roots):
            has_response_assertion = True
    return has_status_assertion and has_response_assertion


def _uses_sample_payload(api_test: dict[str, Any], fact: ApiDocFact) -> bool:
    expected_params = set(fact.business_param_names)
    expected_params.update(str(name) for name in (fact.request_sample or {}).keys())
    expected_params.difference_update(COMMON_QUERY_PARAMS)
    if not expected_params:
        return True

    payload = _payload_text(api_test)
    return any(param in payload for param in expected_params)


def _payload_text(api_test: dict[str, Any]) -> str:
    parts = [str(api_test.get("url") or "")]
    for key in ("body", "formFields", "headers", "variables"):
        value = api_test.get(key)
        if isinstance(value, str):
            parts.append(value)
        else:
            try:
                parts.append(json.dumps(value, ensure_ascii=False))
            except TypeError:
                parts.append(str(value))
    return "\n".join(parts)
