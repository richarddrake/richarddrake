from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from app.auth.security import COOKIE_NAME, AuthTokenError, decode_access_token
from app.auth.service import public_user
from app.services.database import get_user_by_id


def require_login(request: Request) -> dict[str, Any]:
    token = request.cookies.get(COOKIE_NAME) or _bearer_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录。")

    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub") or 0)
    except (AuthTokenError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录。") from exc

    user = get_user_by_id(user_id)
    if not user or not user.get("isActive"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用，请重新登录。")
    return user


def require_admin(current_user: dict[str, Any] = Depends(require_login)) -> dict[str, Any]:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限。")
    return current_user


def current_public_user(current_user: dict[str, Any] = Depends(require_login)) -> dict[str, Any]:
    return public_user(current_user) or {}


def _bearer_token(request: Request) -> str:
    value = request.headers.get("authorization", "")
    prefix = "Bearer "
    if value.startswith(prefix):
        return value[len(prefix) :].strip()
    return ""
