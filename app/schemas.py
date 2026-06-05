from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class UploadedImage:
    filename: str
    content_type: str
    data: bytes

    @property
    def size_kb(self) -> float:
        return round(len(self.data) / 1024, 1)

    def as_data_url(self) -> str:
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.content_type};base64,{encoded}"


@dataclass
class TestCase:
    id: str
    module: str
    title: str
    priority: str
    case_type: str
    scenario: str
    preconditions: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    expected_results: list[str] = field(default_factory=list)
    test_data: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_case(payload: dict[str, Any], index: int) -> TestCase:
    """Accepts slightly varied LLM field names and returns a stable case shape."""
    case_id = str(payload.get("id") or payload.get("case_id") or f"TC-{index:03d}")
    case_type = str(
        payload.get("case_type")
        or payload.get("test_type")
        or payload.get("type")
        or "功能"
    )
    expected = (
        payload.get("expected_results")
        or payload.get("expected_result")
        or payload.get("expected")
        or payload.get("assertions")
        or []
    )
    test_data = payload.get("test_data") or payload.get("data") or ""

    return TestCase(
        id=case_id,
        module=str(payload.get("module") or payload.get("feature") or "核心流程"),
        title=str(payload.get("title") or payload.get("name") or f"测试用例 {index}"),
        priority=str(payload.get("priority") or "P1"),
        case_type=case_type,
        scenario=str(payload.get("scenario") or payload.get("description") or ""),
        preconditions=_as_list(payload.get("preconditions") or payload.get("precondition")),
        steps=_as_list(payload.get("steps") or payload.get("actions")),
        expected_results=_as_list(expected),
        test_data=_stringify(test_data),
        tags=_as_list(payload.get("tags") or payload.get("coverage")),
        source=str(payload.get("source") or payload.get("basis") or ""),
    )


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_stringify(item) for item in value if _stringify(item)]
    if isinstance(value, tuple):
        return [_stringify(item) for item in value if _stringify(item)]
    text = _stringify(value)
    if not text:
        return []
    lines = [part.strip(" -\t") for part in text.replace("；", "\n").splitlines()]
    return [line for line in lines if line]


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list, tuple)):
        return str(value)
    return str(value).strip()
