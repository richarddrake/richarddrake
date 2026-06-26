from __future__ import annotations

import os
import re
from typing import Any

from app.auth.security import hash_password, password_policy_errors
from app.services.database import create_user_account, get_user_by_username, init_auth_store


USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,80}$")


def init_auth_system() -> None:
    init_auth_store()
    ensure_default_admin()


def ensure_default_admin() -> dict[str, Any] | None:
    username = os.getenv("APP_ADMIN_USERNAME", "admin").strip() or "admin"
    display_name = os.getenv("APP_ADMIN_DISPLAY_NAME", "管理员").strip() or "管理员"
    password = os.getenv("APP_ADMIN_PASSWORD", "Admin@123456")

    existing = get_user_by_username(username)
    if existing:
        return public_user(existing)

    created = create_user_account(
        username=username,
        password_hash=hash_password(password),
        display_name=display_name,
        role="admin",
        is_active=True,
    )
    return public_user(created) if created else None


def validate_username(username: str) -> str:
    normalized = " ".join((username or "").strip().lower().split())
    if not USERNAME_PATTERN.match(normalized):
        raise ValueError("用户名只能包含字母、数字、下划线、点和短横线，长度 3-80 位。")
    return normalized


def validate_role(role: str) -> str:
    normalized = (role or "tester").strip().lower()
    if normalized not in {"admin", "tester"}:
        raise ValueError("角色只能是 admin 或 tester。")
    return normalized


def validate_password_policy(password: str) -> None:
    errors = password_policy_errors(password)
    if errors:
        raise ValueError(" ".join(errors))


def public_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user:
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "displayName": user.get("displayName") or user["username"],
        "role": user.get("role") or "tester",
        "isActive": bool(user.get("isActive")),
        "createdAt": user.get("createdAt") or "",
        "updatedAt": user.get("updatedAt") or "",
        "lastLoginAt": user.get("lastLoginAt") or "",
    }
