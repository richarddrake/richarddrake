# 这个模块负责提供 FastAPI 主入口，并统一暴露生成、导出、历史记录和接口执行相关 API。
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import require_login
from app.auth.router import router as auth_router
from app.auth.service import init_auth_system
from app.schemas import UploadedMaterial, normalize_case
from app.services.api_runner import run_api_load_test, run_api_test, run_api_test_suite
from app.services.case_quality import build_coverage_report, enrich_case_dict, enrich_cases
from app.services.case_review import build_case_review
from app.services.database import (
    get_database_status,
    get_history_detail,
    init_database,
    list_api_test_runs,
    list_history,
    list_ui_test_runs,
    record_api_test_run,
    record_generation_session,
    record_ui_test_run,
)
from app.services.excel_exporter import save_cases_to_excel
from app.services.failure_agent import analyze_failure
from app.services.feishu_reader import build_feishu_context, fetch_feishu_references
from app.services.generator import GenerationEvent, generate_test_cases
from app.services.material_parser import build_material_context, read_upload_materials
from app.services.openapi_importer import generate_cases_from_openapi
from app.services.ui_runner import run_ui_test


BASE_DIR = Path(__file__).resolve().parent.parent
GENERATED_DIR = BASE_DIR / "generated"
UI_ARTIFACTS_DIR = GENERATED_DIR / "ui-runs"


def _cors_origins() -> list[str]:
    configured = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if configured:
        return [item.strip() for item in configured.split(",") if item.strip()]
    return [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ]


class ApiTestRunRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str = Field(default="", max_length=255)
    method: str = Field(default="GET", max_length=16)
    url: str = Field(..., min_length=1)
    headers: dict[str, Any] = Field(default_factory=dict)
    body: str = ""
    body_mode: str = Field(default="raw", alias="bodyMode")
    form_fields: dict[str, Any] = Field(default_factory=dict, alias="formFields")
    files: list[dict[str, Any]] = Field(default_factory=list)
    expected_status: int | None = Field(default=200, alias="expectedStatus")
    expected_contains: str = Field(default="", alias="expectedContains")
    max_response_ms: float | None = Field(default=None, alias="maxResponseMs")
    timeout_seconds: float = Field(default=10, alias="timeoutSeconds")
    variables: dict[str, Any] = Field(default_factory=dict)
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    extractors: list[dict[str, Any]] = Field(default_factory=list)
    json_schema: dict[str, Any] | None = Field(default=None, alias="jsonSchema")
    database_assertions: list[dict[str, Any]] = Field(default_factory=list, alias="databaseAssertions")


class ApiTestSuiteRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str = Field(default="接口用例集", max_length=255)
    variables: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    stop_on_failure: bool = Field(default=False, alias="stopOnFailure")


class ApiLoadTestRequest(ApiTestRunRequest):
    repeat: int = Field(default=10, ge=1, le=100)
    concurrency: int = Field(default=3, ge=1, le=20)


class GeneratedCaseExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    case: dict[str, Any] = Field(default_factory=dict)
    api_test: dict[str, Any] = Field(default_factory=dict, alias="apiTest")
    variables: dict[str, Any] = Field(default_factory=dict)


class OpenApiImportRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    content: str = ""
    url: str = ""
    base_url: str = Field(default="", alias="baseUrl")


class CoverageAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    cases: list[dict[str, Any]] = Field(default_factory=list)


class CaseReviewRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    cases: list[dict[str, Any]] = Field(default_factory=list)


class UiTestRunRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str = Field(default="Web UI 自动化用例", max_length=255)
    base_url: str = Field(default="", alias="baseUrl")
    browser: str = Field(default="chromium", max_length=32)
    headless: bool = True
    viewport: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    timeout_seconds: float = Field(default=30, alias="timeoutSeconds")
    step_timeout_ms: float = Field(default=8000, alias="stepTimeoutMs")
    capture_trace: bool = Field(default=True, alias="captureTrace")
    capture_screenshot: bool = Field(default=True, alias="captureScreenshot")
    continue_on_failure: bool = Field(default=False, alias="continueOnFailure")


app = FastAPI(title="测试用例智能生成系统", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)


@app.on_event("startup")
def startup() -> None:
    init_database()
    init_auth_system()


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "测试用例智能生成系统 API",
        "docs": "/docs",
    }


@app.get("/api/database/status", dependencies=[Depends(require_login)])
async def database_status() -> dict:
    return get_database_status()


@app.get("/api/history", dependencies=[Depends(require_login)])
async def history(
    limit: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default=""),
) -> dict:
    return list_history(limit=limit, keyword=keyword)


@app.get("/api/history/{session_id}", dependencies=[Depends(require_login)])
async def history_detail(session_id: str) -> dict:
    detail = get_history_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="历史记录不存在，或 MySQL 暂不可用。")
    return detail


@app.post("/api/api-tests/run", dependencies=[Depends(require_login)])
async def run_api_test_case(request: ApiTestRunRequest) -> dict:
    try:
        result = await run_api_test(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not result.get("passed"):
        result["failureAnalysis"] = analyze_failure(result)
    history_status = await asyncio.to_thread(record_api_test_run, result)
    result["historyStatus"] = history_status
    return result


@app.post("/api/api-tests/suite", dependencies=[Depends(require_login)])
async def run_api_test_suite_case(request: ApiTestSuiteRequest) -> dict:
    try:
        result = await run_api_test_suite(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not result.get("passed"):
        result["failureAnalysis"] = analyze_failure(result)
    history_status = await asyncio.to_thread(record_api_test_run, result)
    result["historyStatus"] = history_status
    return result


@app.post("/api/api-tests/load", dependencies=[Depends(require_login)])
async def run_api_load_test_case(request: ApiLoadTestRequest) -> dict:
    try:
        result = await run_api_load_test(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not result.get("passed"):
        result["failureAnalysis"] = analyze_failure(result)
    history_status = await asyncio.to_thread(record_api_test_run, result)
    result["historyStatus"] = history_status
    return result


@app.get("/api/api-tests/history", dependencies=[Depends(require_login)])
async def api_test_history(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    return list_api_test_runs(limit=limit)


@app.post("/api/ui-tests/run", dependencies=[Depends(require_login)])
async def run_ui_test_case(request: UiTestRunRequest) -> dict:
    try:
        result = await run_ui_test(request.model_dump(by_alias=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    history_status = await asyncio.to_thread(record_ui_test_run, result)
    result["historyStatus"] = history_status
    return result


@app.get("/api/ui-tests/history", dependencies=[Depends(require_login)])
async def ui_test_history(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    return list_ui_test_runs(limit=limit)


@app.get("/api/ui-tests/artifacts/{run_id}/{filename}", dependencies=[Depends(require_login)])
async def ui_test_artifact(run_id: str, filename: str) -> FileResponse:
    safe_run_id = Path(run_id).name
    safe_filename = Path(filename).name
    if safe_run_id != run_id or safe_filename != filename:
        raise HTTPException(status_code=400, detail="文件路径不合法。")
    if not run_id.startswith("UI-") or safe_filename not in {"failure.png", "trace.zip"}:
        raise HTTPException(status_code=400, detail="UI 自动化证据文件不合法。")

    path = UI_ARTIFACTS_DIR / safe_run_id / safe_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="证据文件不存在或已过期。")

    media_type = "image/png" if safe_filename.endswith(".png") else "application/zip"
    return FileResponse(path, media_type=media_type, filename=safe_filename)


@app.post("/api/cases/execute", dependencies=[Depends(require_login)])
async def execute_generated_case(request: GeneratedCaseExecuteRequest) -> dict:
    payload = _case_api_payload(request.case, request.api_test, request.variables)
    try:
        result = await run_api_test(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result["caseId"] = request.case.get("id") or request.case.get("case_id") or ""
    result["caseTitle"] = request.case.get("title") or payload.get("name") or ""
    result["failureAnalysis"] = analyze_failure(result, request.case)
    history_status = await asyncio.to_thread(record_api_test_run, result)
    result["historyStatus"] = history_status
    return result


@app.post("/api/openapi/import", dependencies=[Depends(require_login)])
async def import_openapi(request: OpenApiImportRequest) -> dict:
    try:
        data = await generate_cases_from_openapi(
            content=request.content,
            url=request.url,
            base_url=request.base_url,
        )
        session_id = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]
        cases = enrich_cases([normalize_case(item, index + 1) for index, item in enumerate(data.get("cases") or [])])
        excel_path = save_cases_to_excel(cases, GENERATED_DIR, session_id)
        history_status = await asyncio.to_thread(
            record_generation_session,
            session_id=session_id,
            requirements=f"OpenAPI 导入：{data.get('title') or ''}",
            context=f"接口数量 {data.get('operationCount', 0)}，基础地址 {data.get('baseUrl', '')}",
            references=request.url or "OpenAPI pasted content",
            materials=[],
            cases=cases,
            excel_path=excel_path,
        )
        data["cases"] = [case.to_dict() for case in cases]
        data["coverageReport"] = build_coverage_report(cases)
        data["sessionId"] = session_id
        data["downloadUrl"] = f"/api/download/{excel_path.name}"
        data["historyStatus"] = history_status
        return data
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"读取 OpenAPI URL 失败：{exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/coverage/analyze", dependencies=[Depends(require_login)])
async def analyze_coverage(request: CoverageAnalyzeRequest) -> dict:
    enriched = [enrich_case_dict(item, request.cases) for item in request.cases]
    return build_coverage_report(enriched)


@app.post("/api/cases/review", dependencies=[Depends(require_login)])
async def review_cases(request: CaseReviewRequest) -> dict:
    enriched = [enrich_case_dict(item, request.cases) for item in request.cases]
    return build_case_review(enriched)


@app.post("/api/generate", dependencies=[Depends(require_login)])
async def generate(
    requirements: str = Form(default=""),
    context: str = Form(default=""),
    references: str = Form(default=""),
    files: Optional[list[UploadFile]] = File(default=None),
    images: Optional[list[UploadFile]] = File(default=None),
) -> StreamingResponse:
    uploaded_files = [*(files or []), *(images or [])]
    materials = await read_upload_materials(uploaded_files)
    if not materials and not requirements.strip() and not context.strip() and not references.strip():
        raise HTTPException(status_code=400, detail="请至少上传材料、填写需求背景或粘贴文档链接。")

    session_id = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]
    stream = _stream_generation(session_id, requirements, context, references, materials)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/download/{filename}", dependencies=[Depends(require_login)])
async def download(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="文件名不合法。")

    path = GENERATED_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在或已过期。")

    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"测试用例_{safe_name.removeprefix('test_cases_')}",
    )


async def _stream_generation(
    session_id: str,
    requirements: str,
    context: str,
    references: str,
    materials: list[UploadedMaterial],
) -> AsyncIterator[str]:
    cases = []
    yield _sse("status", {"text": f"已接收 {len(materials)} 个材料，正在解析多源信息与业务约束。"})
    for material in materials:
        yield _sse("thought", {"text": f"材料：{material.describe()}"})

    feishu_results = []
    if references.strip():
        yield _sse("thought", {"text": "正在检查外部链接，并尝试读取已配置授权的飞书文档。"})
        try:
            feishu_results = await fetch_feishu_references(references)
            for result in feishu_results:
                yield _sse("thought", {"text": result.to_status_text()})
        except Exception as exc:
            yield _sse("thought", {"text": f"飞书链接读取已跳过：{type(exc).__name__}"})

    material_context = build_material_context(materials, references)
    feishu_context = build_feishu_context(feishu_results)
    if feishu_context:
        material_context = "\n\n".join(part for part in [material_context, feishu_context] if part).strip()

    try:
        async for event in generate_test_cases(requirements, context, references, materials, material_context):
            if event.kind == "case":
                case = normalize_case(event.payload, len(cases) + 1)
                case = enrich_cases([*cases, case])[-1]
                cases.append(case)
                yield _sse("case", case.to_dict())
            elif event.kind in {"thought", "status"}:
                yield _sse("thought", event.payload)
            else:
                yield _sse(event.kind, event.payload)

        cases = enrich_cases(cases)
        coverage_report = build_coverage_report(cases)
        yield _sse("cases", {"items": [case.to_dict() for case in cases]})
        yield _sse("coverage", coverage_report)

        excel_path = save_cases_to_excel(cases, GENERATED_DIR, session_id)
        history_status = await asyncio.to_thread(
            record_generation_session,
            session_id=session_id,
            requirements=requirements,
            context=context,
            references=references,
            materials=materials,
            cases=cases,
            excel_path=excel_path,
        )
        if history_status == "saved":
            yield _sse("thought", {"text": "历史记录已写入 MySQL。"})
        elif history_status == "disabled":
            yield _sse("thought", {"text": "MySQL 历史记录未启用，当前结果仅保存为 Excel。"})
        else:
            yield _sse("thought", {"text": "MySQL 暂不可用，当前结果已保存为 Excel。"})

        yield _sse(
            "done",
            {
                "sessionId": session_id,
                "count": len(cases),
                "downloadUrl": f"/api/download/{excel_path.name}",
                "historyStatus": history_status,
                "coverageReport": coverage_report,
            },
        )
    except Exception as exc:
        yield _sse("error", {"message": f"生成失败：{exc}"})


def _sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _case_api_payload(case: dict[str, Any], api_test: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    payload = dict(api_test or case.get("api_test") or case.get("apiTest") or {})
    if not payload:
        raise HTTPException(status_code=400, detail="这条用例没有可执行的 api_test 配置。")
    if not payload.get("method") or not payload.get("url"):
        raise HTTPException(status_code=400, detail="api_test 必须包含 method 和 url。")
    payload["name"] = payload.get("name") or case.get("title") or f"{payload.get('method')} {payload.get('url')}"
    payload_variables = payload.get("variables") if isinstance(payload.get("variables"), dict) else {}
    payload["variables"] = {**payload_variables, **variables}
    return payload
