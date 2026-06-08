from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any

from app.schemas import TestCase


COVERAGE_BUCKETS = {
    "requirement": ["需求", "主流程", "正向", "业务", "流程"],
    "interface": ["接口", "api", "http", "openapi", "swagger"],
    "field": ["字段", "表单", "参数", "必填", "格式", "长度"],
    "exception": ["异常", "失败", "错误", "超时", "回退", "恢复"],
    "permission": ["权限", "角色", "授权", "未登录", "token", "鉴权"],
    "boundary": ["边界", "最大", "最小", "超长", "为空", "临界"],
    "data": ["数据", "一致", "落库", "导出", "列表", "详情"],
    "performance": ["性能", "并发", "耗时", "响应时间", "吞吐"],
    "security": ["安全", "注入", "越权", "敏感", "脱敏", "csrf", "xss"],
}


def enrich_cases(cases: list[TestCase]) -> list[TestCase]:
    title_counts = Counter(_fingerprint(case.title) for case in cases)
    enriched: list[TestCase] = []
    for case in cases:
        case_dict = case.to_dict()
        coverage = case.coverage or classify_coverage(case_dict)
        quality = case.quality or score_case(case_dict, title_counts)
        enriched.append(
            replace(
                case,
                coverage_type=case.coverage_type or coverage.get("primary", ""),
                coverage=coverage,
                quality=quality,
            )
        )
    return enriched


def enrich_case_dict(case: dict[str, Any], peer_cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    peers = peer_cases or [case]
    title_counts = Counter(_fingerprint(item.get("title", "")) for item in peers)
    enriched = dict(case)
    enriched.setdefault("coverage", classify_coverage(enriched))
    enriched.setdefault("coverage_type", enriched["coverage"].get("primary", "requirement"))
    enriched.setdefault("quality", score_case(enriched, title_counts))
    return enriched


def build_coverage_report(cases: list[TestCase] | list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [_case_to_dict(case) for case in cases]
    total = len(normalized)
    bucket_hits = {key: 0 for key in COVERAGE_BUCKETS}
    priority_hits: dict[str, int] = {}
    module_hits: dict[str, int] = {}
    automation_ready = 0
    quality_scores: list[int] = []
    matrix: list[dict[str, Any]] = []

    for case in normalized:
        coverage = case.get("coverage") if isinstance(case.get("coverage"), dict) else classify_coverage(case)
        quality = case.get("quality") if isinstance(case.get("quality"), dict) else score_case(case, Counter())
        quality_scores.append(int(quality.get("score") or 0))
        if case.get("api_test") or case.get("apiTest"):
            automation_ready += 1
        priority = str(case.get("priority") or "P1")
        module = str(case.get("module") or "核心流程")
        priority_hits[priority] = priority_hits.get(priority, 0) + 1
        module_hits[module] = module_hits.get(module, 0) + 1
        for bucket in coverage.get("buckets", []):
            if bucket in bucket_hits:
                bucket_hits[bucket] += 1
        matrix.append(
            {
                "id": case.get("id", ""),
                "title": case.get("title", ""),
                "module": module,
                "priority": priority,
                "coverage": coverage.get("buckets", []),
                "qualityScore": quality.get("score", 0),
                "automationReady": bool(case.get("api_test") or case.get("apiTest")),
            }
        )

    ratios = {
        key: {
            "covered": value,
            "total": total,
            "ratio": round(value / total, 4) if total else 0,
        }
        for key, value in bucket_hits.items()
    }
    uncovered = [key for key, value in bucket_hits.items() if total and value == 0]
    risks = _coverage_risks(ratios, automation_ready, total)
    average_quality = round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else 0

    return {
        "totalCases": total,
        "averageQualityScore": average_quality,
        "automationReady": automation_ready,
        "automationRatio": round(automation_ready / total, 4) if total else 0,
        "priorityMix": priority_hits,
        "moduleMix": module_hits,
        "coverage": ratios,
        "uncovered": uncovered,
        "risks": risks,
        "matrix": matrix,
    }


def score_case(case: dict[str, Any], title_counts: Counter[str]) -> dict[str, Any]:
    issues: list[str] = []
    suggestions: list[str] = []

    steps = _as_list(case.get("steps"))
    expected = _as_list(case.get("expected_results") or case.get("expected"))
    test_data = str(case.get("test_data") or "").strip()
    tags = _as_list(case.get("tags"))
    api_test = _as_dict(case.get("api_test") or case.get("apiTest"))
    assertions = _as_list(api_test.get("assertions")) if api_test else []
    expected_status = api_test.get("expectedStatus") or api_test.get("expected_status") if api_test else None
    schema = api_test.get("jsonSchema") or api_test.get("json_schema") if api_test else None

    dimensions = {
        "steps": 20 if len(steps) >= 3 else 12 if steps else 0,
        "expected": 20 if _has_verifiable_expected(expected) else 10 if expected else 0,
        "testData": 15 if len(test_data) >= 6 else 6 if test_data else 0,
        "coverage": 15 if len(tags) >= 2 else 8 if tags else 0,
        "automation": 20 if _is_executable_api(api_test) and (assertions or expected_status or schema) else 12 if _is_executable_api(api_test) else 0,
        "uniqueness": 10,
    }

    fingerprint = _fingerprint(str(case.get("title") or ""))
    if fingerprint and title_counts.get(fingerprint, 0) > 1:
        dimensions["uniqueness"] = 0
        issues.append("标题与其他用例重复，容易造成评审和执行混淆。")
        suggestions.append("拆分触发条件、测试数据或断言点，让重复标题变成可区分的验证目标。")

    if dimensions["steps"] < 20:
        issues.append("步骤不够可执行。")
        suggestions.append("补充明确入口、操作动作和观察点，最好达到 3 步以上。")
    if dimensions["expected"] < 20:
        issues.append("预期结果可验证性不足。")
        suggestions.append("把预期写成状态码、字段值、页面状态、数据库记录或明确提示文案。")
    if dimensions["testData"] < 15:
        issues.append("测试数据不完整。")
        suggestions.append("补充账号、参数组合、边界值或样例请求体。")
    if dimensions["coverage"] < 15:
        suggestions.append("补充覆盖标签，例如主流程、异常、边界、权限、数据一致性。")
    if dimensions["automation"] < 20:
        suggestions.append("如属于接口场景，补充 method、url、headers、body、assertions 和 jsonSchema。")

    score = sum(dimensions.values())
    return {
        "score": max(0, min(100, score)),
        "level": "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D",
        "dimensions": dimensions,
        "issues": issues[:5],
        "suggestions": suggestions[:5],
        "automationReady": dimensions["automation"] >= 20,
    }


def classify_coverage(case: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        [
            str(case.get("module") or ""),
            str(case.get("title") or ""),
            str(case.get("case_type") or ""),
            str(case.get("scenario") or ""),
            " ".join(_as_list(case.get("tags"))),
            " ".join(_as_list(case.get("steps"))),
            " ".join(_as_list(case.get("expected_results"))),
        ]
    ).lower()
    buckets = []
    for key, keywords in COVERAGE_BUCKETS.items():
        if any(keyword.lower() in text for keyword in keywords):
            buckets.append(key)
    if case.get("api_test") or case.get("apiTest"):
        if "interface" not in buckets:
            buckets.append("interface")
    if not buckets:
        buckets.append("requirement")
    return {
        "primary": buckets[0],
        "buckets": buckets,
        "labels": [_bucket_label(bucket) for bucket in buckets],
    }


def _coverage_risks(ratios: dict[str, dict[str, Any]], automation_ready: int, total: int) -> list[str]:
    risks: list[str] = []
    for key in ["interface", "field", "exception", "permission", "boundary"]:
        if ratios.get(key, {}).get("covered", 0) == 0:
            risks.append(f"{_bucket_label(key)}覆盖缺失，建议补充对应类型用例。")
    if total and automation_ready == 0:
        risks.append("暂无可自动执行接口用例，生成结果还没有打通执行闭环。")
    elif total and automation_ready / total < 0.25:
        risks.append("可自动执行用例占比偏低，接口回归自动化收益有限。")
    return risks[:8]


def _case_to_dict(case: TestCase | dict[str, Any]) -> dict[str, Any]:
    return case.to_dict() if isinstance(case, TestCase) else dict(case)


def _is_executable_api(api_test: dict[str, Any]) -> bool:
    return bool(api_test.get("method") and api_test.get("url"))


def _has_verifiable_expected(expected: list[Any]) -> bool:
    if not expected:
        return False
    joined = " ".join(str(item) for item in expected)
    signals = ["状态", "字段", "等于", "包含", "不包含", "显示", "返回", "保存", "落库", "HTTP", "200", "400", "成功", "失败"]
    return any(signal.lower() in joined.lower() for signal in signals)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fingerprint(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _bucket_label(bucket: str) -> str:
    labels = {
        "requirement": "需求",
        "interface": "接口",
        "field": "字段",
        "exception": "异常",
        "permission": "权限",
        "boundary": "边界",
        "data": "数据一致性",
        "performance": "性能",
        "security": "安全",
    }
    return labels.get(bucket, bucket)
