"""
Сообщения: REST — история чата; WebSocket — отправка и мгновенная доставка.

Права:
  direct  — нельзя писать, если хотя бы один из двух заблокировал другого.
  group   — писать может любой участник группы (любая роль).
  channel — писать может только owner или admin канала; читать (историю
            через REST, и получать broadcast через WS) — любой подписчик.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user, get_current_user_ws
from ..database import SessionLocal, get_db
from ..utils import direct_chat_id, is_blocked
from ..ws_manager import manager

router = APIRouter(tags=["messages"])


def _to_out(msg: models.Message) -> schemas.MessageOut:
    return schemas.MessageOut(
        id=msg.id,
        chat_type=msg.chat_type.value,
        chat_id=msg.chat_id,
        sender_id=msg.sender_id,
        sender_username=msg.sender.username,
        text=msg.text,
        created_at=msg.created_at,
    )


# --------------------------------------------------------------------------
# REST: список диалогов для вкладки «Чаты»
# --------------------------------------------------------------------------
@router.get("/messages/conversations", response_model=list[schemas.ConversationOut])
def list_conversations(me: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Личные чаты, в которых у меня есть хотя бы одно сообщение, отсортированные
    по последнему сообщению — то, что показывает вкладка «Чаты».

    chat_id для direct-чата кодирует пару участников (см. utils.direct_chat_id),
    поэтому здесь мы декодируем его обратно, чтобы понять, кто собеседник —
    отдельной таблицы «участники чата» для direct-чатов нет и не нужна.
    """
    lo_expr = models.Message.chat_id / 100_000_000
    hi_expr = models.Message.chat_id % 100_000_000
    mine = (lo_expr == me.id) | (hi_expr == me.id)

    last_ids = (
        db.query(models.Message.chat_id, func.max(models.Message.id).label("last_id"))
        .filter(models.Message.chat_type == models.ChatType.direct, mine)
        .group_by(models.Message.chat_id)
        .subquery()
    )
    rows = (
        db.query(models.Message)
        .join(last_ids, models.Message.id == last_ids.c.last_id)
        .order_by(models.Message.id.desc())
        .all()
    )

    out = []
    for msg in rows:
        lo, hi = divmod(msg.chat_id, 100_000_000)
        peer_id = hi if lo == me.id else lo
        peer = db.get(models.User, peer_id)
        if not peer:
            continue  # собеседник удалил аккаунт — молча пропускаем строку
        out.append(schemas.ConversationOut(peer=peer, last_message=_to_out(msg)))
    return out


# --------------------------------------------------------------------------
# REST: история сообщений
# --------------------------------------------------------------------------
def _history(db: Session, chat_type: models.ChatType, chat_id: int, before_id: int | None, limit: int):
    q = db.query(models.Message).filter_by(
        chat_type=chat_type, chat_id=chat_id, is_deleted=False
    )
    if before_id:
        q = q.filter(models.Message.id < before_id)
    rows = q.order_by(models.Message.id.desc()).limit(limit).all()
    return [_to_out(m) for m in reversed(rows)]


@router.get("/messages/direct/{username}", response_model=list[schemas.MessageOut])
def direct_history(
    username: str,
    before_id: int | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    me: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.query(models.User).filter_by(username=username.lstrip("@").lower()).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    chat_id = direct_chat_id(me.id, target.id)
    return _history(db, models.ChatType.direct, chat_id, before_id, limit)


@router.get("/messages/group/{group_id}", response_model=list[schemas.MessageOut])
def group_history(
    group_id: int,
    before_id: int | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    me: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member = db.query(models.GroupMember).filter_by(group_id=group_id, user_id=me.id).first()
    if not member:
        raise HTTPException(status_code=403, detail="Вы не участник этой группы")
    return _history(db, models.ChatType.group, group_id, before_id, limit)


@router.get("/messages/channel/{channel_id}", response_model=list[schemas.MessageOut])
def channel_history(
    channel_id: int,
    before_id: int | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    me: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = db.query(models.ChannelSubscriber).filter_by(channel_id=channel_id, user_id=me.id).first()
    if not sub:
        raise HTTPException(status_code=403, detail="Вы не подписаны на этот канал")
    return _history(db, models.ChatType.channel, channel_id, before_id, limit)


# --------------------------------------------------------------------------
# WebSocket: реальный обмен сообщениями
# --------------------------------------------------------------------------
async def _handle_direct(db: Session, sender: models.User, incoming: schemas.WSIncoming) -> models.Message:
    if not incoming.to_username:
        raise ValueError("Укажите to_username для личного сообщения")
    target = db.query(models.User).filter_by(username=incoming.to_username.lstrip("@").lower()).first()
    if not target:
        raise ValueError("Получатель не найден")
    if target.id == sender.id:
        raise ValueError("Нельзя написать самому себе")
    if is_blocked(db, sender.id, target.id):
        raise ValueError("Доставка невозможна: пользователь в чёрном списке")

    msg = models.Message(
        chat_type=models.ChatType.direct,
        chat_id=direct_chat_id(sender.id, target.id),
        sender_id=sender.id,
        text=incoming.text,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    msg.sender = sender  # избежать лишнего запроса на relationship
    await manager.send_to_users([sender.id, target.id], _to_out(msg).model_dump(mode="json"))
    return msg


async def _handle_group(db: Session, sender: models.User, incoming: schemas.WSIncoming) -> models.Message:
    if not incoming.group_id:
        raise ValueError("Укажите group_id")
    member = db.query(models.GroupMember).filter_by(group_id=incoming.group_id, user_id=sender.id).first()
    if not member:
        raise ValueError("Вы не участник этой группы")

    msg = models.Message(
        chat_type=models.ChatType.group, chat_id=incoming.group_id, sender_id=sender.id, text=incoming.text
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    msg.sender = sender

    member_ids = [
        m.user_id for m in db.query(models.GroupMember).filter_by(group_id=incoming.group_id).all()
    ]
    await manager.send_to_users(member_ids, _to_out(msg).model_dump(mode="json"))
    return msg


async def _handle_channel(db: Session, sender: models.User, incoming: schemas.WSIncoming) -> models.Message:
    if not incoming.channel_id:
        raise ValueError("Укажите channel_id")
    sub = db.query(models.ChannelSubscriber).filter_by(
        channel_id=incoming.channel_id, user_id=sender.id
    ).first()
    if not sub or sub.role not in (models.ChannelRole.owner, models.ChannelRole.admin):
        raise ValueError("Публиковать в канал могут только владелец и администраторы")

    msg = models.Message(
        chat_type=models.ChatType.channel, chat_id=incoming.channel_id, sender_id=sender.id, text=incoming.text
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    msg.sender = sender

    subscriber_ids = [
        s.user_id for s in db.query(models.ChannelSubscriber).filter_by(channel_id=incoming.channel_id).all()
    ]
    await manager.send_to_users(subscriber_ids, _to_out(msg).model_dump(mode="json"))
    return msg


_HANDLERS = {"direct": _handle_direct, "group": _handle_group, "channel": _handle_channel}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    user = await get_current_user_ws(websocket)  # кидает WebSocketException до accept, если токен плохой
    await manager.connect(user.id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            db = SessionLocal()
            try:
                try:
                    data = json.loads(raw)
                    incoming = schemas.WSIncoming(**data)
                except (json.JSONDecodeError, ValidationError) as e:
                    await websocket.send_text(json.dumps({"error": f"Неверный формат: {e}"}))
                    continue

                handler = _HANDLERS[incoming.chat_type]
                try:
                    await handler(db, user, incoming)
                except ValueError as e:
                    await websocket.send_text(json.dumps({"error": str(e)}))
            finally:
                db.close()
    except WebSocketDisconnect:
        manager.disconnect(user.id, websocket)
