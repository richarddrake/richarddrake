# 这个模块负责把测试用例导出为 Markdown 文件，便于提交评审、归档和项目汇报。
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.schemas import TestCase


def save_cases_to_markdown(
    cases: list[TestCase],
    target_dir: Path,
    session_id: str,
    title: str = "测试用例",
) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    content = build_cases_markdown(cases, title=title, session_id=session_id)
    path = target_dir / f"test_cases_{session_id}.md"
    path.write_text(content, encoding="utf-8")
    return path


def build_cases_markdown(cases: list[TestCase], title: str = "测试用例", session_id: str = "") -> str:
    priority_counter = Counter(case.priority or "未标注" for case in cases)
    type_counter = Counter(case.case_type or "未标注" for case in cases)
    modules: dict[str, list[TestCase]] = defaultdict(list)
    for case in cases:
        modules[case.module or "核心流程"].append(case)

    lines = [
        f"# {title}",
        "",
        "## 概览",
        "",
        f"- 会话 ID：{session_id or '-'}",
        f"- 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 用例总数：{len(cases)}",
        f"- 模块数量：{len(modules)}",
        f"- 优先级分布：{_counter_text(priority_counter)}",
        f"- 用例类型分布：{_counter_text(type_counter)}",
        "",
        "## 模块目录",
        "",
    ]

    for module, items in modules.items():
        lines.append(f"- {module}：{len(items)} 条")

    lines.extend(["", "## 用例明细", ""])

    for module, items in modules.items():
        lines.extend([f"### {module}", ""])
        for case in items:
            lines.extend(_case_markdown(case))

    return "\n".join(lines).strip() + "\n"


def _case_markdown(case: TestCase) -> list[str]:
    lines = [
        f"#### {case.id} {case.title}",
        "",
        f"- 优先级：{case.priority or '-'}",
        f"- 类型：{case.case_type or '-'}",
        f"- 需求追溯：{case.requirement_id or '-'}",
        f"- 覆盖场景：{case.scenario or '-'}",
        f"- 标签：{', '.join(case.tags) if case.tags else '-'}",
        f"- 依据：{case.source or '-'}",
        "",
        "**前置条件**",
        "",
        *_list_lines(case.preconditions),
        "",
        "**操作步骤**",
        "",
        *_list_lines(case.steps),
        "",
        "**预期结果**",
        "",
        *_list_lines(case.expected_results),
        "",
        "**测试数据**",
        "",
        _code_block(case.test_data or "-"),
        "",
    ]

    if case.api_test:
        lines.extend(["**可执行接口配置**", "", _code_block(_json_text(case.api_test), "json"), ""])
    if case.ui_test:
        lines.extend(["**可执行 UI 配置**", "", _code_block(_json_text(case.ui_test), "json"), ""])
    if case.quality:
        lines.extend(["**质量评分**", "", _code_block(_json_text(case.quality), "json"), ""])
    return lines


def _list_lines(values: list[str]) -> list[str]:
    if not values:
        return ["- -"]
    return [f"{index}. {value}" for index, value in enumerate(values, 1)]


def _counter_text(counter: Counter[str]) -> str:
    if not counter:
        return "-"
    return "，".join(f"{key} {value}" for key, value in sorted(counter.items()))


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _code_block(value: str, language: str = "") -> str:
    text = str(value or "").replace("```", "'''")
    return f"```{language}\n{text}\n```"
