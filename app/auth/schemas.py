from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    username: str = Field(..., min_length=3, max_length=80)
    password: str = Field(..., min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=120, alias="displayName")
    role: str = Field(default="tester", max_length=32)
    is_active: bool = Field(default=True, alias="isActive")


class UserStatusRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    is_active: bool = Field(..., alias="isActive")


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    old_password: str = Field(..., min_length=1, max_length=200, alias="oldPassword")
    new_password: str = Field(..., min_length=8, max_length=200, alias="newPassword")
