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


# ---------- Группы ----------

class GroupCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    member_usernames: list[str] = Field(default_factory=list)


class GroupMemberOut(BaseModel):
    user: UserOut
    role: str

    class Config:
        from_attributes = True


class GroupOut(BaseModel):
    id: int
    title: str
    owner_id: int
    created_at: datetime
    members: list[GroupMemberOut] = []

    class Config:
        from_attributes = True


# ---------- Каналы ----------

class ChannelCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    username: str | None = Field(default=None, min_length=5, max_length=32)
    description: str | None = None

    @field_validator("username")
    @classmethod
    def username_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.lstrip("@")
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Юзернейм канала: 5-32 символа, только латиница, цифры и подчёркивание"
            )
        return v.lower()


class ChannelOut(BaseModel):
    id: int
    title: str
    username: str | None
    description: str | None
    owner_id: int
    is_recommended: bool
    subscriber_count: int = 0
    my_role: str | None = None  # роль текущего пользователя, если он подписан

    class Config:
        from_attributes = True


# ---------- Сообщения ----------

class MessageOut(BaseModel):
    id: int
    chat_type: str
    chat_id: int
    sender_id: int
    sender_username: str
    text: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    """Одна строка в списке 'Чаты': собеседник + последнее сообщение."""
    peer: UserOut
    last_message: MessageOut


class WSIncoming(BaseModel):
    """Формат сообщения, которое клиент шлёт в WebSocket."""
    chat_type: str  # "direct" | "group" | "channel"
    text: str = Field(min_length=1, max_length=4096)
    to_username: str | None = None  # для chat_type="direct"
    group_id: int | None = None      # для chat_type="group"
    channel_id: int | None = None    # для chat_type="channel"

    @field_validator("chat_type")
    @classmethod
    def valid_chat_type(cls, v: str) -> str:
        if v not in ("direct", "group", "channel"):
            raise ValueError("chat_type должен быть direct, group или channel")
        return v
