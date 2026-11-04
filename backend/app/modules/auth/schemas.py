from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=8, max_length=512)
    display_name: str = Field(min_length=1, max_length=150)


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    # Development may accept a local operator id which the router maps to an
    # internal email. Registration still requires a real email-shaped value.
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=512)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    is_active: bool


class SessionInfo(BaseModel):
    authenticated: bool
    user: UserOut | None = None
    csrf_token: str | None = None


class MessageOut(BaseModel):
    message: str
