# 这个模块负责把生成用例整理成面向评审会的结论、问题和修改建议。
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from app.services.case_quality import enrich_case_dict


BLOCKING_PRIORITIES = {"P0", "P1"}


def build_case_review(cases: list[dict[str, Any]]) -> dict[str, Any]:
    enriched = [enrich_case_dict(case, cases) for case in cases]
    duplicate_groups = _duplicate_title_groups(enriched)
    duplicate_titles = {group["fingerprint"] for group in duplicate_groups}
    items = [_review_case(case, duplicate_titles) for case in enriched]
    status_counts = Counter(item["status"] for item in items)
    severity_counts = Counter(item["severity"] for item in items)
    issue_counts = Counter(issue for item in items for issue in item["issues"])
    total = len(items)
    approved = status_counts.get("approved", 0)
    needs_revision = status_counts.get("needs_revision", 0)
    blocked = status_counts.get("blocked", 0)
    average_score = round(sum(item["qualityScore"] for item in items) / total, 1) if total else 0

    if blocked:
        verdict = "阻塞"
        verdict_level = "block"
        verdict_reason = "存在高优先级、不可执行或预期不可验证的用例，建议修改后再进入执行。"
    elif needs_revision:
        verdict = "需修改"
        verdict_level = "warn"
        verdict_reason = "多数用例可以评审，但仍有追溯、步骤、数据或断言需要补齐。"
    elif total:
        verdict = "通过"
        verdict_level = "pass"
        verdict_reason = "当前用例整体具备进入执行或归档的条件。"
    else:
        verdict = "待评审"
        verdict_level = "empty"
        verdict_reason = "当前还没有可评审的用例。"

    return {
        "totalCases": total,
        "approved": approved,
        "needsRevision": needs_revision,
        "blocked": blocked,
        "averageQualityScore": average_score,
        "verdict": verdict,
        "verdictLevel": verdict_level,
        "verdictReason": verdict_reason,
        "statusCounts": dict(status_counts),
        "severityCounts": dict(severity_counts),
        "topIssues": [{"issue": issue, "count": count} for issue, count in issue_counts.most_common(6)],
        "duplicateGroups": duplicate_groups,
        "checklist": _build_checklist(enriched, items),
        "recommendations": _recommendations(items, duplicate_groups, issue_counts),
        "items": items,
    }


def _review_case(case: dict[str, Any], duplicate_titles: set[str]) -> dict[str, Any]:
    quality = case.get("quality") if isinstance(case.get("quality"), dict) else {}
    readiness = quality.get("executionReadiness") if isinstance(quality.get("executionReadiness"), dict) else {}
    score = int(quality.get("score") or 0)
    priority = str(case.get("priority") or "P1").upper()
    case_id = str(case.get("id") or "")
    duplicated = _fingerprint(case.get("title")) in duplicate_titles
    issues = _case_issues(case, quality, readiness, duplicated)
    actions = _case_actions(case, quality, readiness, duplicated)

    has_blocker = (
        score < 55
        or (priority in BLOCKING_PRIORITIES and score < 70)
        or readiness.get("status") == "needs_info"
        or _missing_core_content(case)
    )
    if has_blocker:
        status = "blocked"
        severity = "high" if priority in BLOCKING_PRIORITIES else "medium"
    elif score < 80 or issues:
        status = "needs_revision"
        severity = "medium" if priority in BLOCKING_PRIORITIES else "low"
    else:
        status = "approved"
        severity = "low"

    return {
        "id": case_id,
        "title": str(case.get("title") or "未命名用例"),
        "module": str(case.get("module") or "核心流程"),
        "priority": priority,
        "caseType": str(case.get("case_type") or case.get("caseType") or "功能"),
        "requirementId": str(case.get("requirement_id") or case.get("requirementId") or ""),
        "qualityScore": score,
        "qualityLevel": str(quality.get("level") or "-"),
        "status": status,
        "severity": severity,
        "readinessLabel": str(readiness.get("label") or "未评估"),
        "readinessReason": str(readiness.get("reason") or ""),
        "issues": issues[:6],
        "actions": actions[:6],
    }


def _case_issues(
    case: dict[str, Any],
    quality: dict[str, Any],
    readiness: dict[str, Any],
    duplicated: bool,
) -> list[str]:
    issues: list[str] = []
    if duplicated:
        issues.append("标题或验证目标重复")
    if not str(case.get("requirement_id") or case.get("requirementId") or "").strip():
        issues.append("缺少需求追溯")
    if _missing_core_content(case):
        issues.append("步骤或预期结果不完整")
    if readiness.get("status") == "needs_info":
        issues.append("接口执行信息未补齐")
    issues.extend(str(item) for item in quality.get("issues") or [])
    for deduction in quality.get("deductions") or []:
        if isinstance(deduction, dict) and deduction.get("lost", 0) >= 8:
            issues.append(str(deduction.get("label") or "质量扣分项"))
    return _unique(issues)


def _case_actions(
    case: dict[str, Any],
    quality: dict[str, Any],
    readiness: dict[str, Any],
    duplicated: bool,
) -> list[str]:
    actions: list[str] = []
    if duplicated:
        actions.append("拆分触发条件、测试数据或断言点，让重复用例可区分。")
    if not str(case.get("requirement_id") or case.get("requirementId") or "").strip():
        actions.append("补充需求编号或来源章节，方便评审追溯。")
    if readiness.get("status") == "needs_info":
        missing = ", ".join(str(item) for item in readiness.get("missing") or [])
        actions.append(f"补齐接口执行配置：{missing or 'method、url、断言'}。")
    actions.extend(str(item) for item in quality.get("suggestions") or [])
    if not actions:
        actions.append("保持当前用例结构，可进入执行或归档。")
    return _unique(actions)


def _build_checklist(cases: list[dict[str, Any]], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = len(cases)
    traced = sum(1 for case in cases if str(case.get("requirement_id") or case.get("requirementId") or "").strip())
    complete_steps = sum(1 for case in cases if len(_as_list(case.get("steps"))) >= 3)
    verifiable_expected = sum(1 for case in cases if _as_list(case.get("expected_results") or case.get("expected")))
    executable = sum(1 for item in items if item.get("readinessLabel") == "可执行")
    approved = sum(1 for item in items if item.get("status") == "approved")

    return [
        _checklist_item("需求追溯", traced, total, "每条用例应能回到需求编号、章节或材料来源。"),
        _checklist_item("步骤完整", complete_steps, total, "建议包含入口、操作动作和观察点。"),
        _checklist_item("预期可验证", verifiable_expected, total, "预期结果应能通过页面状态、接口响应或数据结果验证。"),
        _checklist_item("执行就绪", executable, total, "接口类用例需要具备 method、url 和断言。"),
        _checklist_item("评审通过", approved, total, "通过项可进入执行、导出或归档。"),
    ]


def _checklist_item(label: str, passed: int, total: int, suggestion: str) -> dict[str, Any]:
    ratio = round(passed / total, 4) if total else 0
    return {
        "label": label,
        "passed": passed,
        "total": total,
        "ratio": ratio,
        "status": "pass" if total and ratio >= 0.8 else "warn" if total and ratio >= 0.5 else "block",
        "suggestion": suggestion,
    }


def _recommendations(
    items: list[dict[str, Any]],
    duplicate_groups: list[dict[str, Any]],
    issue_counts: Counter[str],
) -> list[str]:
    recommendations: list[str] = []
    if duplicate_groups:
        recommendations.append("先处理重复标题或重复验证目标，避免评审时误以为覆盖充分。")
    if any(item["status"] == "blocked" for item in items):
        recommendations.append("优先修改阻塞项，尤其是 P0/P1 用例的步骤、预期和接口执行配置。")
    for issue, _count in issue_counts.most_common(3):
        recommendations.append(f"集中补齐：{issue}。")
    if not recommendations and items:
        recommendations.append("当前用例整体质量较好，可进入执行验证并沉淀到历史记录。")
    return _unique(recommendations)[:6]


def _duplicate_title_groups(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        fingerprint = " ".join(str(case.get("title") or "").strip().lower().split())
        if fingerprint:
            groups[fingerprint].append(case)
    return [
        {
            "fingerprint": _fingerprint(items[0].get("title")),
            "title": items[0].get("title") or "",
            "caseIds": [str(item.get("id") or "") for item in items],
            "count": len(items),
        }
        for items in groups.values()
        if len(items) > 1
    ]


def _missing_core_content(case: dict[str, Any]) -> bool:
    return not _as_list(case.get("steps")) or not _as_list(case.get("expected_results") or case.get("expected"))


def _fingerprint(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        normalized = " ".join(str(value or "").split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_values.append(normalized)
    return unique_values
