from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class UploadedMaterial:
    filename: str
    content_type: str
    data: bytes
    kind: str = "file"
    extracted_text: str = ""
    note: str = ""

    @property
    def size_kb(self) -> float:
        return round(len(self.data) / 1024, 1)

    @property
    def is_image(self) -> bool:
        return self.content_type.startswith("image/")

    def as_data_url(self) -> str:
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.content_type};base64,{encoded}"

    def describe(self) -> str:
        text_state = "已抽取文本" if self.extracted_text else "无可抽取文本"
        if self.note:
            text_state = self.note
        return f"{self.filename} ({self.kind}, {self.content_type}, {self.size_kb} KB, {text_state})"


UploadedImage = UploadedMaterial


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
    requirement_id: str = ""
    source_type: str = ""
    coverage_type: str = ""
    api_test: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    failure_analysis: dict[str, Any] = field(default_factory=dict)

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
    api_test = _api_test_from_payload(payload)

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
        requirement_id=str(payload.get("requirement_id") or payload.get("requirementId") or ""),
        source_type=str(payload.get("source_type") or payload.get("sourceType") or ""),
        coverage_type=str(payload.get("coverage_type") or payload.get("coverageType") or ""),
        api_test=api_test,
        quality=_as_dict(payload.get("quality")),
        coverage=_as_dict(payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}),
        execution=_as_dict(payload.get("execution")),
        failure_analysis=_as_dict(payload.get("failure_analysis") or payload.get("failureAnalysis")),
    )


def _api_test_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    explicit = payload.get("api_test") or payload.get("apiTest") or payload.get("api")
    if isinstance(explicit, dict):
        return explicit

    method = payload.get("method")
    url = payload.get("url") or payload.get("endpoint")
    if not method or not url:
        return {}

    return {
        "name": payload.get("title") or payload.get("name") or "",
        "method": method,
        "url": url,
        "headers": _as_dict(payload.get("headers")),
        "body": payload.get("body") or "",
        "bodyMode": payload.get("body_mode") or payload.get("bodyMode") or "raw",
        "expectedStatus": payload.get("expected_status") or payload.get("expectedStatus") or 200,
        "expectedContains": payload.get("expected_contains") or payload.get("expectedContains") or "",
        "assertions": payload.get("api_assertions") or payload.get("assertions") or [],
        "extractors": payload.get("extractors") or [],
        "databaseAssertions": payload.get("database_assertions") or payload.get("databaseAssertions") or [],
        "jsonSchema": payload.get("json_schema") or payload.get("jsonSchema") or None,
        "variables": _as_dict(payload.get("variables")),
        "timeoutSeconds": payload.get("timeout_seconds") or payload.get("timeoutSeconds") or 10,
    }


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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list, tuple)):
        return str(value)
    return str(value).strip()
