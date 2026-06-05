from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.schemas import UploadedImage, normalize_case
from app.services.excel_exporter import save_cases_to_excel
from app.services.generator import GenerationEvent, generate_test_cases


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
GENERATED_DIR = BASE_DIR / "generated"
MAX_IMAGE_BYTES = 12 * 1024 * 1024

app = FastAPI(title="测试用例智能生成系统", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/api/generate")
async def generate(
    requirements: str = Form(default=""),
    context: str = Form(default=""),
    images: Optional[list[UploadFile]] = File(default=None),
) -> StreamingResponse:
    uploaded_images = await _read_images(images or [])
    if not uploaded_images and not requirements.strip() and not context.strip():
        raise HTTPException(status_code=400, detail="请至少上传一张图片或填写需求背景。")

    session_id = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]
    stream = _stream_generation(session_id, requirements, context, uploaded_images)
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


async def _read_images(files: list[UploadFile]) -> list[UploadedImage]:
    uploaded_images: list[UploadedImage] = []
    for file in files:
        if not file.filename:
            continue
        content_type = file.content_type or "application/octet-stream"
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"{file.filename} 不是图片文件。")
        data = await file.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail=f"{file.filename} 超过 12MB。")
        uploaded_images.append(
            UploadedImage(filename=file.filename, content_type=content_type, data=data)
        )
    return uploaded_images


async def _stream_generation(
    session_id: str,
    requirements: str,
    context: str,
    images: list[UploadedImage],
) -> AsyncIterator[str]:
    cases = []
    yield _sse("status", {"text": "材料已接收，正在解析视觉信息与业务约束。"})

    try:
        async for event in generate_test_cases(requirements, context, images):
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
