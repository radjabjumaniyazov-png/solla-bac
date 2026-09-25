from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/channels", tags=["channels"])


def _get_sub(db: Session, channel_id: int, user_id: int) -> models.ChannelSubscriber | None:
    return db.query(models.ChannelSubscriber).filter_by(channel_id=channel_id, user_id=user_id).first()


def _out(db: Session, channel: models.Channel, me_id: int | None = None) -> schemas.ChannelOut:
    count = db.query(models.ChannelSubscriber).filter_by(channel_id=channel.id).count()
    my_role = None
    if me_id is not None:
        sub = _get_sub(db, channel.id, me_id)
        my_role = sub.role.value if sub else None
    return schemas.ChannelOut(
        id=channel.id,
        title=channel.title,
        username=channel.username,
        description=channel.description,
        owner_id=channel.owner_id,
        is_recommended=channel.is_recommended,
        subscriber_count=count,
        my_role=my_role,
    )


@router.post("", response_model=schemas.ChannelOut, status_code=201)
def create_channel(
    data: schemas.ChannelCreate,
    me: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.username:
        taken = db.query(models.Channel).filter_by(username=data.username).first()
        if taken:
            raise HTTPException(status_code=409, detail="Такой юзернейм канала уже занят")

    channel = models.Channel(
        title=data.title, username=data.username, description=data.description, owner_id=me.id
    )
    db.add(channel)
    db.flush()
    db.add(models.ChannelSubscriber(channel_id=channel.id, user_id=me.id, role=models.ChannelRole.owner))
    db.commit()
    db.refresh(channel)
    return _out(db, channel, me.id)


@router.get("/recommended", response_model=list[schemas.ChannelOut])
def recommended_channels(
    me: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    channels = db.query(models.Channel).filter_by(is_recommended=True).limit(20).all()
    return [_out(db, c, me.id) for c in channels]


@router.get("/search", response_model=list[schemas.ChannelOut])
def search_channels(
    q: str, me: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    rows = (
        db.query(models.Channel)
        .filter(
            (models.Channel.title.ilike(f"%{q}%")) | (models.Channel.username.ilike(f"%{q}%"))
        )
        .limit(20)
        .all()
    )
    return [_out(db, c, me.id) for c in rows]


@router.get("/mine", response_model=list[schemas.ChannelOut])
def my_channels(me: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Каналы, на которые подписан (включая свои собственные, где роль owner/admin)."""
    subs = db.query(models.ChannelSubscriber).filter_by(user_id=me.id).all()
    channels = [db.get(models.Channel, s.channel_id) for s in subs]
    return [_out(db, c, me.id) for c in channels if c]


@router.post("/{channel_id}/subscribe", response_model=schemas.ChannelOut)
def subscribe(
    channel_id: int, me: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    channel = db.get(models.Channel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Канал не найден")
    if not _get_sub(db, channel_id, me.id):
        db.add(models.ChannelSubscriber(channel_id=channel_id, user_id=me.id, role=models.ChannelRole.subscriber))
        db.commit()
    return _out(db, channel, me.id)


@router.delete("/{channel_id}/subscribe")
def unsubscribe(
    channel_id: int, me: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    sub = _get_sub(db, channel_id, me.id)
    if sub:
        if sub.role == models.ChannelRole.owner:
            raise HTTPException(
                status_code=400, detail="Владелец не может отписаться от собственного канала"
            )
        db.delete(sub)
        db.commit()
    return {"ok": True}


@router.patch("/{channel_id}/admins/{username}")
def set_admin(
    channel_id: int,
    username: str,
    make_admin: bool,
    me: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Только владелец канала может назначать/снимать админов."""
    my_sub = _get_sub(db, channel_id, me.id)
    if not my_sub or my_sub.role != models.ChannelRole.owner:
        raise HTTPException(status_code=403, detail="Назначать админов может только владелец канала")

    target = db.query(models.User).filter_by(username=username.lstrip("@").lower()).first()
    target_sub = target and _get_sub(db, channel_id, target.id)
    if not target_sub:
        raise HTTPException(status_code=404, detail="Пользователь не подписан на канал")

    target_sub.role = models.ChannelRole.admin if make_admin else models.ChannelRole.subscriber
    db.commit()
    return {"ok": True}
