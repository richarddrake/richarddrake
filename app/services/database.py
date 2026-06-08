from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.schemas import TestCase, UploadedMaterial


load_dotenv()

Base = declarative_base()
JsonText = Text().with_variant(LONGTEXT, "mysql")

_engine = None
_SessionLocal = None
_last_error = ""


class GenerationSession(Base):
    __tablename__ = "generation_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(80), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    requirements = Column(JsonText, nullable=False, default="")
    context = Column(JsonText, nullable=False, default="")
    references = Column(JsonText, nullable=False, default="")
    material_count = Column(Integer, nullable=False, default=0)
    case_count = Column(Integer, nullable=False, default=0)
    excel_filename = Column(String(255), nullable=False, default="")
    download_url = Column(String(500), nullable=False, default="")
    status = Column(String(32), nullable=False, default="completed")
    summary = Column(JsonText, nullable=False, default="")

    materials = relationship("GenerationMaterial", cascade="all, delete-orphan", back_populates="session")
    cases = relationship("StoredTestCase", cascade="all, delete-orphan", back_populates="session")


class GenerationMaterial(Base):
    __tablename__ = "generation_materials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(80), ForeignKey("generation_sessions.session_id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False, default="")
    content_type = Column(String(160), nullable=False, default="")
    kind = Column(String(64), nullable=False, default="file")
    size_kb = Column(String(32), nullable=False, default="")
    note = Column(String(500), nullable=False, default="")
    extracted_text_preview = Column(JsonText, nullable=False, default="")

    session = relationship("GenerationSession", back_populates="materials")


class StoredTestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(80), ForeignKey("generation_sessions.session_id"), nullable=False, index=True)
    case_id = Column(String(80), nullable=False, index=True)
    module = Column(String(255), nullable=False, default="")
    title = Column(String(500), nullable=False, default="")
    priority = Column(String(32), nullable=False, default="P1")
    case_type = Column(String(80), nullable=False, default="功能")
    scenario = Column(JsonText, nullable=False, default="")
    preconditions_json = Column(JsonText, nullable=False, default="[]")
    steps_json = Column(JsonText, nullable=False, default="[]")
    expected_results_json = Column(JsonText, nullable=False, default="[]")
    test_data = Column(JsonText, nullable=False, default="")
    tags_json = Column(JsonText, nullable=False, default="[]")
    source = Column(JsonText, nullable=False, default="")
    raw_json = Column(JsonText, nullable=False, default="{}")

    session = relationship("GenerationSession", back_populates="cases")


def init_database() -> bool:
    global _engine, _SessionLocal, _last_error
    if not is_database_enabled():
        _last_error = ""
        return False

    if _engine is None:
        database_url = get_database_url()
        if not database_url:
            _last_error = "DATABASE_URL 或 MySQL 连接环境变量未配置。"
            return False

        _engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)

    try:
        Base.metadata.create_all(bind=_engine)
        _last_error = ""
        return True
    except SQLAlchemyError as exc:
        _last_error = str(exc)
        return False


def get_database_status() -> dict[str, Any]:
    if not is_database_enabled():
        return {
            "enabled": False,
            "connected": False,
            "message": "MySQL 未启用。请在 .env 中配置 DATABASE_ENABLED=true 和 MySQL 连接信息。",
        }

    if not init_database():
        return {"enabled": True, "connected": False, "message": _last_error or "MySQL 初始化失败。"}

    try:
        with _engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"enabled": True, "connected": True, "message": "MySQL 连接正常。"}
    except SQLAlchemyError as exc:
        return {"enabled": True, "connected": False, "message": str(exc)}


def record_generation_session(
    *,
    session_id: str,
    requirements: str,
    context: str,
    references: str,
    materials: list[UploadedMaterial],
    cases: list[TestCase],
    excel_path: Path,
) -> str:
    if not is_database_enabled():
        return "disabled"
    if not init_database():
        return "unavailable"

    try:
        with _SessionLocal() as db:
            existing = db.query(GenerationSession).filter(GenerationSession.session_id == session_id).one_or_none()
            if existing:
                db.delete(existing)
                db.flush()

            session = GenerationSession(
                session_id=session_id,
                created_at=datetime.utcnow(),
                requirements=requirements,
                context=context,
                references=references,
                material_count=len(materials),
                case_count=len(cases),
                excel_filename=excel_path.name,
                download_url=f"/api/download/{excel_path.name}",
                status="completed",
                summary=_build_summary(requirements, context, references, materials, cases),
            )
            db.add(session)

            for material in materials:
                db.add(
                    GenerationMaterial(
                        session_id=session_id,
                        filename=material.filename,
                        content_type=material.content_type,
                        kind=material.kind,
                        size_kb=str(material.size_kb),
                        note=material.note,
                        extracted_text_preview=(material.extracted_text or "")[:1200],
                    )
                )

            for case in cases:
                item = case.to_dict()
                db.add(
                    StoredTestCase(
                        session_id=session_id,
                        case_id=case.id,
                        module=case.module,
                        title=case.title,
                        priority=case.priority,
                        case_type=case.case_type,
                        scenario=case.scenario,
                        preconditions_json=_json_dumps(case.preconditions),
                        steps_json=_json_dumps(case.steps),
                        expected_results_json=_json_dumps(case.expected_results),
                        test_data=case.test_data,
                        tags_json=_json_dumps(case.tags),
                        source=case.source,
                        raw_json=_json_dumps(item),
                    )
                )

            db.commit()
        return "saved"
    except SQLAlchemyError as exc:
        global _last_error
        _last_error = str(exc)
        return "failed"


def list_history(limit: int = 20, keyword: str = "") -> dict[str, Any]:
    if not is_database_enabled():
        return {"enabled": False, "connected": False, "message": "MySQL 未启用。", "items": []}
    if not init_database():
        return {"enabled": True, "connected": False, "message": _last_error, "items": []}

    safe_limit = max(1, min(limit, 100))
    keyword = keyword.strip()

    try:
        with _SessionLocal() as db:
            query = db.query(GenerationSession).order_by(GenerationSession.created_at.desc())
            if keyword:
                like_value = f"%{keyword}%"
                query = query.filter(
                    GenerationSession.session_id.like(like_value)
                    | GenerationSession.requirements.like(like_value)
                    | GenerationSession.context.like(like_value)
                    | GenerationSession.references.like(like_value)
                )
            sessions = query.limit(safe_limit).all()
            return {
                "enabled": True,
                "connected": True,
                "message": "ok",
                "items": [_session_summary(item) for item in sessions],
            }
    except SQLAlchemyError as exc:
        return {"enabled": True, "connected": False, "message": str(exc), "items": []}


def get_history_detail(session_id: str) -> dict[str, Any] | None:
    if not is_database_enabled() or not init_database():
        return None

    try:
        with _SessionLocal() as db:
            session = db.query(GenerationSession).filter(GenerationSession.session_id == session_id).one_or_none()
            if not session:
                return None
            return {
                **_session_summary(session),
                "requirements": session.requirements,
                "context": session.context,
                "references": session.references,
                "materials": [_material_to_dict(item) for item in session.materials],
                "cases": [_case_to_dict(item) for item in session.cases],
            }
    except SQLAlchemyError:
        return None


def is_database_enabled() -> bool:
    return os.getenv("DATABASE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def get_database_url() -> str:
    explicit_url = os.getenv("DATABASE_URL", "").strip()
    if explicit_url:
        return explicit_url

    host = os.getenv("MYSQL_HOST", "").strip()
    user = os.getenv("MYSQL_USER", "").strip()
    database = os.getenv("MYSQL_DATABASE", "").strip()
    if not host or not user or not database:
        return ""

    port = os.getenv("MYSQL_PORT", "3306").strip() or "3306"
    password = os.getenv("MYSQL_PASSWORD", "")
    charset = os.getenv("MYSQL_CHARSET", "utf8mb4").strip() or "utf8mb4"
    return (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{database}?charset={quote_plus(charset)}"
    )


def _session_summary(session: GenerationSession) -> dict[str, Any]:
    return {
        "sessionId": session.session_id,
        "createdAt": session.created_at.isoformat() + "Z" if session.created_at else "",
        "requirementsSummary": _compact(session.requirements),
        "contextSummary": _compact(session.context),
        "materialCount": session.material_count,
        "caseCount": session.case_count,
        "excelFilename": session.excel_filename,
        "downloadUrl": session.download_url,
        "status": session.status,
        "summary": _load_json(session.summary, {}),
    }


def _material_to_dict(material: GenerationMaterial) -> dict[str, Any]:
    return {
        "filename": material.filename,
        "contentType": material.content_type,
        "kind": material.kind,
        "sizeKb": material.size_kb,
        "note": material.note,
        "extractedTextPreview": material.extracted_text_preview,
    }


def _case_to_dict(case: StoredTestCase) -> dict[str, Any]:
    raw = _load_json(case.raw_json, {})
    if raw:
        return raw
    return {
        "id": case.case_id,
        "module": case.module,
        "title": case.title,
        "priority": case.priority,
        "case_type": case.case_type,
        "scenario": case.scenario,
        "preconditions": _load_json(case.preconditions_json, []),
        "steps": _load_json(case.steps_json, []),
        "expected_results": _load_json(case.expected_results_json, []),
        "test_data": case.test_data,
        "tags": _load_json(case.tags_json, []),
        "source": case.source,
    }


def _build_summary(
    requirements: str,
    context: str,
    references: str,
    materials: list[UploadedMaterial],
    cases: list[TestCase],
) -> str:
    priorities: dict[str, int] = {}
    modules: dict[str, int] = {}
    for case in cases:
        priorities[case.priority] = priorities.get(case.priority, 0) + 1
        modules[case.module] = modules.get(case.module, 0) + 1

    payload = {
        "requirements": _compact(requirements),
        "context": _compact(context),
        "references": _compact(references),
        "materials": [material.filename for material in materials[:10]],
        "priorityMix": priorities,
        "modules": modules,
    }
    return _json_dumps(payload)


def _compact(value: str, length: int = 120) -> str:
    text_value = " ".join((value or "").split())
    if len(text_value) <= length:
        return text_value
    return text_value[: length - 1] + "..."


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback
