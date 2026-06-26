from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any


COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "ai_test_access_token")
HASH_ALGORITHM = "pbkdf2_sha256"
HASH_ITERATIONS = 260_000


class AuthTokenError(ValueError):
    """Raised when an access token is missing, expired, or invalid."""


def hash_password(password: str) -> str:
    salt = secrets.token_urlsafe(18)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        HASH_ITERATIONS,
    )
    return f"{HASH_ALGORITHM}${HASH_ITERATIONS}${salt}${base64.urlsafe_b64encode(digest).decode('ascii')}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, encoded_digest = stored_hash.split("$", 3)
        if algorithm != HASH_ALGORITHM:
            return False
        iterations = int(iterations_text)
        expected = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, OSError):
        return False


def create_access_token(user: dict[str, Any]) -> tuple[str, int]:
    now = int(time.time())
    expires_in = _token_expire_seconds()
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "iat": now,
        "exp": now + expires_in,
    }
    return _encode_jwt(payload), expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    parts = (token or "").split(".")
    if len(parts) != 3:
        raise AuthTokenError("登录状态无效。")

    signing_input = ".".join(parts[:2]).encode("ascii")
    expected = _sign(signing_input)
    if not hmac.compare_digest(parts[2], expected):
        raise AuthTokenError("登录状态无效。")

    try:
        payload = json.loads(_base64url_decode(parts[1]).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthTokenError("登录状态无效。") from exc

    if int(payload.get("exp") or 0) < int(time.time()):
        raise AuthTokenError("登录已过期。")
    return payload


def password_policy_errors(password: str) -> list[str]:
    errors = []
    if len(password or "") < 8:
        errors.append("密码至少需要 8 位。")
    if password and password.lower() == password:
        errors.append("密码建议包含大写字母。")
    if password and password.upper() == password:
        errors.append("密码建议包含小写字母。")
    if password and not any(item.isdigit() for item in password):
        errors.append("密码建议包含数字。")
    return errors


def cookie_secure() -> bool:
    return os.getenv("AUTH_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}


def _encode_jwt(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    return f"{encoded_header}.{encoded_payload}.{_sign(signing_input)}"


def _sign(value: bytes) -> str:
    digest = hmac.new(_secret_key().encode("utf-8"), value, hashlib.sha256).digest()
    return _base64url_encode(digest)


def _secret_key() -> str:
    return os.getenv("AUTH_SECRET_KEY", "ai-testcase-dev-secret-change-me")


def _token_expire_seconds() -> int:
    try:
        minutes = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "1440"))
    except ValueError:
        minutes = 1440
    return max(5, min(minutes, 60 * 24 * 30)) * 60


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
