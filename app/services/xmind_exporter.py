# 这个模块负责把测试用例导出为 XMind 思维导图文件，便于按模块和用例层级评审。
from __future__ import annotations

import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas import TestCase


def save_cases_to_xmind(cases: list[TestCase], target_dir: Path, session_id: str, title: str = "测试用例思维导图") -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    sheet_id = _id("sheet")
    content = [
        {
            "id": sheet_id,
            "class": "sheet",
            "title": title,
            "rootTopic": _topic(title, _module_topics(cases)),
            "topicPositioning": "fixed",
        }
    ]
    metadata = {
        "creator": {"name": "AI Testcase Platform", "version": "1.0.0"},
        "created": datetime.now(timezone.utc).isoformat(),
        "activeSheetId": sheet_id,
    }
    manifest = {
        "file-entries": {
            "content.json": {"media-type": "application/json"},
            "metadata.json": {"media-type": "application/json"},
            "manifest.json": {"media-type": "application/json"},
        }
    }

    path = target_dir / f"test_cases_{session_id}.xmind"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("content.json", json.dumps(content, ensure_ascii=False, indent=2))
        archive.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return path


def _module_topics(cases: list[TestCase]) -> list[dict[str, Any]]:
    groups: dict[str, list[TestCase]] = {}
    for case in cases:
        module = _clean_title(case.module or "核心流程")
        groups.setdefault(module, []).append(case)

    topics: list[dict[str, Any]] = []
    for module, items in groups.items():
        topics.append(_topic(f"{module}（{len(items)} 条）", [_case_topic(item) for item in items]))
    return topics


def _case_topic(case: TestCase) -> dict[str, Any]:
    title = " | ".join(part for part in [case.id, case.priority, case.title] if part)
    children: list[dict[str, Any]] = []
    if case.requirement_id:
        children.append(_topic(f"需求追溯：{case.requirement_id}"))
    if case.case_type:
        children.append(_topic(f"用例类型：{case.case_type}"))
    if case.scenario:
        children.append(_topic(f"覆盖场景：{case.scenario}"))

    children.extend(
        item
        for item in [
            _list_topic("前置条件", case.preconditions),
            _list_topic("操作步骤", case.steps),
            _list_topic("预期结果", case.expected_results),
        ]
        if item
    )

    if case.test_data:
        children.append(_topic(f"测试数据：{case.test_data}"))
    if case.tags:
        children.append(_topic("标签", [_topic(str(item)) for item in case.tags]))
    automation = _automation_topics(case)
    if automation:
        children.append(_topic("自动化配置", automation))
    if case.source:
        children.append(_topic(f"依据：{case.source}"))
    return _topic(_clean_title(title), children)


def _automation_topics(case: TestCase) -> list[dict[str, Any]]:
    topics: list[dict[str, Any]] = []
    if case.api_test:
        method = case.api_test.get("method") or ""
        url = case.api_test.get("url") or case.api_test.get("endpoint") or ""
        topics.append(_topic(f"API：{method} {url}".strip()))
    if case.ui_test:
        steps = case.ui_test.get("steps") if isinstance(case.ui_test.get("steps"), list) else []
        topics.append(_topic(f"UI：{len(steps)} 个步骤"))
    return topics


def _list_topic(title: str, values: list[str]) -> dict[str, Any] | None:
    if not values:
        return None
    return _topic(title, [_topic(f"{index}. {value}") for index, value in enumerate(values, 1)])


def _topic(title: str, children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    topic: dict[str, Any] = {
        "id": _id("topic"),
        "class": "topic",
        "title": _clean_title(title),
    }
    if children:
        topic["children"] = {"attached": children}
    return topic


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _clean_title(value: object, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text or "未命名"
    return text[: limit - 1].rstrip() + "…"
