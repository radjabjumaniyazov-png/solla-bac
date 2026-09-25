from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user, hash_password, verify_password
from ..database import get_db

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=schemas.UserOut)
def read_profile(me: models.User = Depends(get_current_user)):
    return me


@router.patch("/me", response_model=schemas.UserOut)
def update_profile(
    data: schemas.ProfileUpdate,
    me: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Смена имени и аватарки."""
    if data.display_name is not None:
        me.display_name = data.display_name
    if data.avatar_url is not None:
        me.avatar_url = data.avatar_url
    db.commit()
    db.refresh(me)
    return me


@router.post("/password")
def change_password(
    data: schemas.PasswordChange,
    me: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.old_password, me.password_hash):
        raise HTTPException(status_code=400, detail="Текущий пароль указан неверно")
    me.password_hash = hash_password(data.new_password)
    db.commit()
    return {"ok": True}


@router.post("/username", response_model=schemas.UserOut)
def change_username(
    data: schemas.UsernameChange,
    me: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    taken = (
        db.query(models.User)
        .filter(models.User.username == data.new_username, models.User.id != me.id)
        .first()
    )
    if taken:
        raise HTTPException(status_code=409, detail="Этот юзернейм уже занят")
    me.username = data.new_username
    db.commit()
    db.refresh(me)
    return me


@router.post("/blacklist/{user_id}")
def block_user(
    user_id: int, me: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if user_id == me.id:
        raise HTTPException(status_code=400, detail="Нельзя заблокировать самого себя")
    if not db.get(models.User, user_id):
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    exists = (
        db.query(models.BlacklistEntry)
        .filter_by(owner_id=me.id, blocked_user_id=user_id)
        .first()
    )
    if not exists:
        db.add(models.BlacklistEntry(owner_id=me.id, blocked_user_id=user_id))
        db.commit()
    return {"ok": True}


@router.delete("/blacklist/{user_id}")
def unblock_user(
    user_id: int, me: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    entry = (
        db.query(models.BlacklistEntry)
        .filter_by(owner_id=me.id, blocked_user_id=user_id)
        .first()
    )
    if entry:
        db.delete(entry)
        db.commit()
    return {"ok": True}


@router.get("/blacklist", response_model=list[schemas.UserOut])
def list_blacklist(me: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    entries = db.query(models.BlacklistEntry).filter_by(owner_id=me.id).all()
    return [db.get(models.User, e.blocked_user_id) for e in entries]
