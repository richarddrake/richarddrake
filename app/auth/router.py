from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.dependencies import current_public_user, require_admin, require_login
from app.auth.schemas import ChangePasswordRequest, CreateUserRequest, LoginRequest, UserStatusRequest
from app.auth.security import COOKIE_NAME, cookie_secure, create_access_token, hash_password, verify_password
from app.auth.service import (
    public_user,
    validate_password_policy,
    validate_role,
    validate_username,
)
from app.services.database import (
    create_user_account,
    get_auth_store_status,
    get_user_by_username,
    list_user_accounts,
    mark_user_login,
    record_login_audit,
    set_user_active,
    update_user_password,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    username = (payload.username or "").strip().lower()
    user = get_user_by_username(username)
    remote_ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")

    if not user or not user.get("isActive") or not verify_password(payload.password, user.get("passwordHash") or ""):
        record_login_audit(
            username=username,
            user_id=user.get("id") if user else None,
            success=False,
            ip_address=remote_ip,
            user_agent=user_agent,
            reason="invalid_credentials_or_inactive",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码不正确。")

    refreshed_user = mark_user_login(int(user["id"])) or user
    token, expires_in = create_access_token(refreshed_user)
    _set_auth_cookie(response, token, expires_in)
    record_login_audit(
        username=username,
        user_id=int(user["id"]),
        success=True,
        ip_address=remote_ip,
        user_agent=user_agent,
        reason="login_success",
    )
    return {"user": public_user(refreshed_user), "expiresIn": expires_in}


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(COOKIE_NAME, path="/", samesite="lax")
    return {"status": "ok"}


@router.get("/me")
async def me(current_user: dict[str, Any] = Depends(current_public_user)) -> dict[str, Any]:
    return {"user": current_user, "authStore": get_auth_store_status()}


@router.get("/users")
async def users(_: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return {"items": [public_user(item) for item in list_user_accounts()]}


@router.post("/users")
async def create_user(payload: CreateUserRequest, _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        username = validate_username(payload.username)
        role = validate_role(payload.role)
        validate_password_policy(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    user = create_user_account(
        username=username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        role=role,
        is_active=payload.is_active,
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在，或认证存储暂不可用。")
    return {"user": public_user(user)}


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    payload: UserStatusRequest,
    current_user: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    if int(current_user["id"]) == user_id and not payload.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用当前登录的管理员账号。")
    user = set_user_active(user_id, payload.is_active)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在。")
    return {"user": public_user(user)}


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: dict[str, Any] = Depends(require_login),
) -> dict[str, str]:
    if not verify_password(payload.old_password, current_user.get("passwordHash") or ""):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="旧密码不正确。")
    try:
        validate_password_policy(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    updated = update_user_password(int(current_user["id"]), hash_password(payload.new_password))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在。")
    return {"status": "ok"}


def _set_auth_cookie(response: Response, token: str, expires_in: int) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=expires_in,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )
