"""
Модели данных под все разделы ТЗ:

  Чаты      -> Message (личные, chat_type="direct")
  Контакты  -> Contact
  Группы    -> Group, GroupMember, Message (chat_type="group")
  Каналы    -> Channel, ChannelSubscriber, Message (chat_type="channel")
  Профиль   -> User
  ЧС        -> BlacklistEntry

Все ID — целые автоинкременты. @username хранится без "@" и с UNIQUE-индексом,
чтобы дубликаты отклонялись на уровне БД, а не только проверкой в коде.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    login = Column(String(64), unique=True, nullable=False, index=True)
    username = Column(String(32), unique=True, nullable=False, index=True)  # без "@"
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(128), nullable=False, default="")
    avatar_url = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    contacts = relationship(
        "Contact", foreign_keys="Contact.owner_id", back_populates="owner",
        cascade="all, delete-orphan",
    )
    blacklisted_by_me = relationship(
        "BlacklistEntry", foreign_keys="BlacklistEntry.owner_id",
        cascade="all, delete-orphan",
    )


class Contact(Base):
    """Запись адресной книги: owner добавил к себе в контакты contact_user."""
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("owner_id", "contact_user_id", name="uq_contact_pair"),)

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    contact_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    alias = Column(String(128), nullable=True)  # необязательное локальное имя контакта
    created_at = Column(DateTime(timezone=True), default=utcnow)

    owner = relationship("User", foreign_keys=[owner_id], back_populates="contacts")
    contact_user = relationship("User", foreign_keys=[contact_user_id])


class BlacklistEntry(Base):
    """owner заблокировал blocked_user."""
    __tablename__ = "blacklist"
    __table_args__ = (UniqueConstraint("owner_id", "blocked_user_id", name="uq_blacklist_pair"),)

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    blocked_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    title = Column(String(128), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")


class GroupRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_member"),)

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(Enum(GroupRole), nullable=False, default=GroupRole.member)
    joined_at = Column(DateTime(timezone=True), default=utcnow)

    group = relationship("Group", back_populates="members")
    user = relationship("User")


class Channel(Base):
    """
    В отличие от группы, в канале по умолчанию писать могут только owner/admin,
    а подписчики только читают — это проверяется в роутере сообщений, а не тут.
    """
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True)
    title = Column(String(128), nullable=False)
    username = Column(String(32), unique=True, nullable=True)  # публичная ссылка @channel, опционально
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_recommended = Column(Boolean, default=False)  # для блока «Рекомендованные каналы»
    created_at = Column(DateTime(timezone=True), default=utcnow)

    subscribers = relationship("ChannelSubscriber", back_populates="channel", cascade="all, delete-orphan")


class ChannelRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    subscriber = "subscriber"


class ChannelSubscriber(Base):
    __tablename__ = "channel_subscribers"
    __table_args__ = (UniqueConstraint("channel_id", "user_id", name="uq_channel_sub"),)

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(Enum(ChannelRole), nullable=False, default=ChannelRole.subscriber)
    joined_at = Column(DateTime(timezone=True), default=utcnow)

    channel = relationship("Channel", back_populates="subscribers")
    user = relationship("User")


class ChatType(str, enum.Enum):
    direct = "direct"    # личный чат
    group = "group"
    channel = "channel"


class Message(Base):
    """
    Универсальная таблица сообщений для всех трёх типов чатов.
    Для direct: chat_id = меньший_user_id * 100000000 + больший_user_id (см. utils),
    чтобы у пары пользователей всегда был один и тот же chat_id независимо от того,
    кто кому написал первым. Для group/channel: chat_id = group.id / channel.id.
    """
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    chat_type = Column(Enum(ChatType), nullable=False)
    chat_id = Column(Integer, nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)
    is_deleted = Column(Boolean, default=False)

    sender = relationship("User")
