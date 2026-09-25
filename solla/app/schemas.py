"""Pydantic-схемы: что принимают и что отдают эндпоинты."""
import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{5,32}$")


class UserRegister(BaseModel):
    login: str = Field(min_length=3, max_length=64)
    username: str = Field(min_length=5, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = None

    @field_validator("username")
    @classmethod
    def username_format(cls, v: str) -> str:
        v = v.lstrip("@")
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Юзернейм: 5-32 символа, только латиница, цифры и подчёркивание"
            )
        return v.lower()

    @field_validator("login")
    @classmethod
    def login_format(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_.@-]+$", v):
            raise ValueError("Логин содержит недопустимые символы")
        return v


class UserLogin(BaseModel):
    login: str
    password: str


class UserOut(BaseModel):
    id: int
    login: str
    username: str
    display_name: str
    avatar_url: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UsernameChange(BaseModel):
    new_username: str = Field(min_length=5, max_length=32)

    @field_validator("new_username")
    @classmethod
    def format_ok(cls, v: str) -> str:
        v = v.lstrip("@")
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Юзернейм: 5-32 символа, только латиница, цифры и подчёркивание"
            )
        return v.lower()


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None
