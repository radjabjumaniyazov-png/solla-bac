from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("/search", response_model=list[schemas.UserOut])
def search_users(
    q: str, me: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Поиск пользователей по юзернейму для экрана 'Добавить контакт'."""
    q = q.lstrip("@")
    return (
        db.query(models.User)
        .filter(models.User.username.ilike(f"%{q}%"), models.User.id != me.id)
        .limit(20)
        .all()
    )


@router.post("/{username}", response_model=schemas.UserOut)
def add_contact(
    username: str, me: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    target = db.query(models.User).filter_by(username=username.lstrip("@").lower()).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь с таким юзернеймом не найден")
    if target.id == me.id:
        raise HTTPException(status_code=400, detail="Нельзя добавить себя в контакты")

    exists = db.query(models.Contact).filter_by(owner_id=me.id, contact_user_id=target.id).first()
    if not exists:
        db.add(models.Contact(owner_id=me.id, contact_user_id=target.id))
        db.commit()
    return target


@router.get("", response_model=list[schemas.UserOut])
def list_contacts(me: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(models.Contact).filter_by(owner_id=me.id).all()
    return [r.contact_user for r in rows]


@router.delete("/{username}")
def remove_contact(
    username: str, me: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    target = db.query(models.User).filter_by(username=username.lstrip("@").lower()).first()
    if target:
        row = db.query(models.Contact).filter_by(owner_id=me.id, contact_user_id=target.id).first()
        if row:
            db.delete(row)
            db.commit()
    return {"ok": True}
