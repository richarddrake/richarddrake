from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app.schemas import UploadedMaterial, normalize_case
from app.services.excel_exporter import save_cases_to_excel
from app.services.generator import GenerationEvent, generate_test_cases
from app.services.material_parser import build_material_context, read_upload_materials


BASE_DIR = Path(__file__).resolve().parent.parent
GENERATED_DIR = BASE_DIR / "generated"

app = FastAPI(title="测试用例智能生成系统", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "测试用例智能生成系统 API",
        "docs": "/docs",
    }


@app.post("/api/generate")
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


@app.get("/api/download/{filename}")
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
    material_context = build_material_context(materials, references)
    yield _sse("status", {"text": f"已接收 {len(materials)} 个材料，正在解析多源信息与业务约束。"})
    for material in materials:
        yield _sse("thought", {"text": f"材料：{material.describe()}"})

    try:
        async for event in generate_test_cases(requirements, context, references, materials, material_context):
            if event.kind == "case":
                case = normalize_case(event.payload, len(cases) + 1)
                cases.append(case)
                yield _sse("case", case.to_dict())
            elif event.kind in {"thought", "status"}:
                yield _sse("thought", event.payload)
            else:
                yield _sse(event.kind, event.payload)

        excel_path = save_cases_to_excel(cases, GENERATED_DIR, session_id)
        yield _sse(
            "done",
            {
                "sessionId": session_id,
                "count": len(cases),
                "downloadUrl": f"/api/download/{excel_path.name}",
            },
        )
    except Exception as exc:
        yield _sse("error", {"message": f"生成失败：{exc}"})


def _sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
