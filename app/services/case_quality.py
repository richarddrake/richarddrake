# 这个模块负责评估测试用例质量、补充覆盖标签，并生成整体覆盖率分析报告。
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

EXECUTION_HINTS = ("接口", "api", "http", "swagger", "openapi", "url", "endpoint")
UI_EXECUTION_HINTS = ("页面", "ui", "web", "浏览器", "按钮", "输入框", "表单", "登录", "点击", "跳转", "playwright")


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
    automation_partial = 0
    automation_manual = 0
    quality_scores: list[int] = []
    quality_levels: dict[str, int] = {}
    issue_counts: Counter[str] = Counter()
    matrix: list[dict[str, Any]] = []

    for case in normalized:
        coverage = case.get("coverage") if isinstance(case.get("coverage"), dict) else classify_coverage(case)
        quality = case.get("quality") if isinstance(case.get("quality"), dict) else score_case(case, Counter())
        readiness = quality.get("executionReadiness") if isinstance(quality.get("executionReadiness"), dict) else assess_execution_readiness(case)
        quality_scores.append(int(quality.get("score") or 0))
        quality_level = str(quality.get("level") or "C")
        quality_levels[quality_level] = quality_levels.get(quality_level, 0) + 1
        issue_counts.update(str(item) for item in quality.get("issues") or [])
        if readiness.get("ready"):
            automation_ready += 1
        elif readiness.get("kind") == "api":
            automation_partial += 1
        else:
            automation_manual += 1
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
                "automationReady": bool(readiness.get("ready")),
                "executionStatus": readiness.get("status", "manual"),
                "executionReason": readiness.get("reason", ""),
                "requirementId": case.get("requirement_id") or case.get("requirementId") or "",
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
    coverage_summary = [
        {
            "key": key,
            "label": _bucket_label(key),
            "covered": value["covered"],
            "total": value["total"],
            "ratio": value["ratio"],
            "description": _coverage_description(key),
        }
        for key, value in ratios.items()
    ]
    uncovered_details = [
        {
            "key": key,
            "label": _bucket_label(key),
            "reason": f"当前结果还没有明显覆盖到{_bucket_label(key)}相关场景。",
            "suggestion": _coverage_suggestion(key),
        }
        for key in uncovered
    ]
    blocked_examples = [
        {
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "reason": item.get("executionReason", ""),
        }
        for item in matrix
        if item.get("executionStatus") == "needs_info"
    ][:6]
    quality_summary = {
        "levels": quality_levels,
        "topIssues": [{"issue": issue, "count": count} for issue, count in issue_counts.most_common(5)],
    }
    recommendations = [*risks]
    recommendations.extend(detail["suggestion"] for detail in uncovered_details[:3])

    return {
        "totalCases": total,
        "averageQualityScore": average_quality,
        "automationReady": automation_ready,
        "automationRatio": round(automation_ready / total, 4) if total else 0,
        "priorityMix": priority_hits,
        "moduleMix": module_hits,
        "coverage": ratios,
        "coverageSummary": coverage_summary,
        "uncovered": uncovered,
        "uncoveredDetails": uncovered_details,
        "risks": risks,
        "recommendations": recommendations[:8],
        "automationSummary": {
            "ready": automation_ready,
            "needsInfo": automation_partial,
            "manual": automation_manual,
            "blockedExamples": blocked_examples,
        },
        "qualitySummary": quality_summary,
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
    ui_test = _as_dict(case.get("ui_test") or case.get("uiTest"))
    readiness = assess_execution_readiness(case)
    assertions = _as_list(api_test.get("assertions")) if api_test else []
    ui_assertions = [step for step in ui_test.get("steps", []) if isinstance(step, dict) and step.get("assertion")] if ui_test else []
    expected_status = api_test.get("expectedStatus") or api_test.get("expected_status") if api_test else None
    schema = api_test.get("jsonSchema") or api_test.get("json_schema") if api_test else None
    requirement_id = str(case.get("requirement_id") or case.get("requirementId") or "").strip()

    dimensions = {
        "steps": 20 if len(steps) >= 3 else 12 if steps else 0,
        "expected": 20 if _has_verifiable_expected(expected) else 10 if expected else 0,
        "testData": 15 if len(test_data) >= 6 else 6 if test_data else 0,
        "coverage": 15 if len(tags) >= 2 else 8 if tags else 0,
        "automation": _automation_score(readiness, assertions, expected_status, schema, ui_assertions),
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
        if readiness.get("kind") == "api":
            suggestions.append("如属于接口场景，补充 method、url、headers、body、assertions 和 jsonSchema。")
        elif readiness.get("kind") == "ui":
            suggestions.append("如属于页面自动化场景，补充 baseUrl、稳定 locator、步骤和页面断言。")
        else:
            suggestions.append("这条用例更适合作为手工测试或评审用例，可保留为非接口执行项。")
    if not requirement_id:
        suggestions.append("补充 requirement_id 或需求编号，方便后续追溯来源。")

    deductions = [
        _dimension_breakdown("steps", "步骤可执行性", dimensions["steps"], 20, "步骤不够清晰，执行人可能无法稳定复现。"),
        _dimension_breakdown("expected", "预期可验证性", dimensions["expected"], 20, "预期结果缺少可验证的状态、字段或落库依据。"),
        _dimension_breakdown("testData", "测试数据完整性", dimensions["testData"], 15, "测试数据样例、边界值或账号信息不足。"),
        _dimension_breakdown("coverage", "覆盖标签完整性", dimensions["coverage"], 15, "覆盖标签偏少，难以看出主流程、异常、边界等范围。"),
        _dimension_breakdown("automation", "执行就绪度", dimensions["automation"], 20, readiness.get("reason", "缺少稳定执行所需的接口配置或断言。")),
        _dimension_breakdown("uniqueness", "重复度", dimensions["uniqueness"], 10, "标题或验证目标与其他用例重复。"),
    ]

    score = sum(dimensions.values())
    return {
        "score": max(0, min(100, score)),
        "level": "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D",
        "dimensions": dimensions,
        "deductions": [item for item in deductions if item["lost"] > 0],
        "issues": issues[:5],
        "suggestions": suggestions[:5],
        "automationReady": dimensions["automation"] >= 20,
        "executionReadiness": readiness,
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


def assess_execution_readiness(case: dict[str, Any]) -> dict[str, Any]:
    api_test = _as_dict(case.get("api_test") or case.get("apiTest"))
    ui_test = _as_dict(case.get("ui_test") or case.get("uiTest"))
    text = " ".join(
        [
            str(case.get("title") or ""),
            str(case.get("module") or ""),
            str(case.get("case_type") or ""),
            str(case.get("scenario") or ""),
            " ".join(_as_list(case.get("tags"))),
        ]
    ).lower()
    is_ui_case = bool(ui_test) or any(hint in text for hint in UI_EXECUTION_HINTS)
    if is_ui_case and not api_test:
        steps = ui_test.get("steps") if isinstance(ui_test.get("steps"), list) else []
        base_url = str(ui_test.get("baseUrl") or ui_test.get("base_url") or "").strip()
        has_goto = any(isinstance(step, dict) and step.get("action") == "goto" and step.get("url") for step in steps)
        has_assertion = any(isinstance(step, dict) and step.get("assertion") for step in steps)
        missing: list[str] = []
        if not ui_test:
            missing.append("ui_test")
        if not steps:
            missing.append("steps")
        if not (base_url or has_goto):
            missing.append("baseUrl 或 goto.url")
        if steps and not has_assertion:
            missing.append("页面断言")
        if missing:
            return {
                "kind": "ui",
                "ready": False,
                "status": "needs_info",
                "label": "UI 待补齐",
                "reason": f"已识别为页面自动化用例，但缺少 {', '.join(missing)}，暂时不能通过 Playwright 稳定执行。",
                "missing": missing,
                "warnings": [],
            }
        return {
            "kind": "ui",
            "ready": True,
            "status": "ready",
            "label": "UI 可执行",
            "reason": "UI 步骤和页面断言已具备执行条件，可送入 Playwright 执行器。",
            "missing": [],
            "warnings": [],
        }

    is_api_case = bool(api_test) or any(hint in text for hint in EXECUTION_HINTS)
    if not is_api_case:
        return {
            "kind": "manual",
            "ready": False,
            "status": "manual",
            "label": "手工用例",
            "reason": "当前更像是手工测试或评审用例，不要求直接通过接口执行器运行。",
            "missing": [],
            "warnings": [],
        }

    missing = [field for field in ["method", "url"] if not str(api_test.get(field) or "").strip()]
    if not api_test:
        missing.insert(0, "api_test")

    assertions = _as_list(api_test.get("assertions")) if api_test else []
    expected_status = api_test.get("expectedStatus") or api_test.get("expected_status") if api_test else None
    schema = api_test.get("jsonSchema") or api_test.get("json_schema") if api_test else None
    warnings: list[str] = []
    if not missing and not (assertions or expected_status or schema):
        warnings.append("虽然 method 和 url 已存在，但断言仍然偏弱，建议补充状态码、JSONPath 或 Schema 校验。")

    if missing:
        readable = ", ".join(missing)
        return {
            "kind": "api",
            "ready": False,
            "status": "needs_info",
            "label": "待补齐",
            "reason": f"已识别为接口相关用例，但缺少 {readable}，暂时不能一键执行。",
            "missing": missing,
            "warnings": warnings,
        }

    return {
        "kind": "api",
        "ready": True,
        "status": "ready",
        "label": "可执行",
        "reason": "接口配置已具备执行条件，可直接送入接口执行器。",
        "missing": [],
        "warnings": warnings,
    }


def _automation_score(
    readiness: dict[str, Any],
    assertions: list[Any],
    expected_status: Any,
    schema: Any,
    ui_assertions: list[Any] | None = None,
) -> int:
    if readiness.get("kind") == "manual":
        return 14
    if readiness.get("kind") == "ui":
        if readiness.get("ready") and ui_assertions:
            return 20
        if readiness.get("ready"):
            return 14
        return 4
    if readiness.get("ready") and (assertions or expected_status or schema):
        return 20
    if readiness.get("ready"):
        return 14
    return 4


def _dimension_breakdown(key: str, label: str, score: int, max_score: int, reason: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "score": score,
        "max": max_score,
        "lost": max(0, max_score - score),
        "reason": reason,
    }


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


def _coverage_description(bucket: str) -> str:
    descriptions = {
        "requirement": "用于确认需求主流程和业务意图是否被覆盖。",
        "interface": "用于确认接口请求、响应和契约层面的测试是否充分。",
        "field": "用于确认字段、表单、参数格式和必填项校验。",
        "exception": "用于确认异常路径、失败恢复和错误提示。",
        "permission": "用于确认登录态、角色权限和鉴权边界。",
        "boundary": "用于确认长度、数值、为空、临界值等边界场景。",
        "data": "用于确认数据一致性、导出、落库和结果回查。",
        "performance": "用于确认耗时、并发和性能风险。",
        "security": "用于确认敏感数据、越权和安全校验。",
    }
    return descriptions.get(bucket, "用于补充当前测试范围。")


def _coverage_suggestion(bucket: str) -> str:
    suggestions = {
        "requirement": "补充主流程、分支流程和角色差异场景。",
        "interface": "补充 method、url、headers、body 和响应断言。",
        "field": "补充必填、格式、非法值和长度限制场景。",
        "exception": "补充错误码、失败提示、超时和回退流程。",
        "permission": "补充未登录、低权限、跨角色访问场景。",
        "boundary": "补充最小值、最大值、临界值和空值场景。",
        "data": "补充数据库校验、导出结果和数据一致性验证。",
        "performance": "补充响应时间阈值、重复执行和并发场景。",
        "security": "补充敏感字段脱敏、越权和恶意输入场景。",
    }
    return suggestions.get(bucket, "补充该维度相关的测试场景。")
