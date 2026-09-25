from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/groups", tags=["groups"])


def _get_membership(db: Session, group_id: int, user_id: int) -> models.GroupMember | None:
    return (
        db.query(models.GroupMember)
        .filter_by(group_id=group_id, user_id=user_id)
        .first()
    )


def _require_member(db: Session, group_id: int, user_id: int) -> models.GroupMember:
    m = _get_membership(db, group_id, user_id)
    if not m:
        raise HTTPException(status_code=403, detail="Вы не участник этой группы")
    return m


@router.post("", response_model=schemas.GroupOut, status_code=201)
def create_group(
    data: schemas.GroupCreate,
    me: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = models.Group(title=data.title, owner_id=me.id)
    db.add(group)
    db.flush()  # получить group.id до commit

    db.add(models.GroupMember(group_id=group.id, user_id=me.id, role=models.GroupRole.owner))

    for username in data.member_usernames:
        user = db.query(models.User).filter_by(username=username.lstrip("@").lower()).first()
        if user and user.id != me.id:
            db.add(models.GroupMember(group_id=group.id, user_id=user.id, role=models.GroupRole.member))

    db.commit()
    return _load_group(db, group.id)


def _load_group(db: Session, group_id: int) -> models.Group:
    return (
        db.query(models.Group)
        .options(joinedload(models.Group.members).joinedload(models.GroupMember.user))
        .filter_by(id=group_id)
        .first()
    )


@router.get("", response_model=list[schemas.GroupOut])
def list_my_groups(me: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = db.query(models.GroupMember).filter_by(user_id=me.id).all()
    return [_load_group(db, m.group_id) for m in memberships]


@router.get("/{group_id}", response_model=schemas.GroupOut)
def get_group(
    group_id: int, me: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _require_member(db, group_id, me.id)
    group = _load_group(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    return group


@router.post("/{group_id}/members/{username}", response_model=schemas.GroupOut)
def add_member(
    group_id: int,
    username: str,
    me: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    my_membership = _require_member(db, group_id, me.id)
    if my_membership.role not in (models.GroupRole.owner, models.GroupRole.admin):
        raise HTTPException(status_code=403, detail="Добавлять участников могут только владелец и админы")

    target = db.query(models.User).filter_by(username=username.lstrip("@").lower()).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if not _get_membership(db, group_id, target.id):
        db.add(models.GroupMember(group_id=group_id, user_id=target.id, role=models.GroupRole.member))
        db.commit()
    return _load_group(db, group_id)


@router.delete("/{group_id}/members/{username}")
def remove_member(
    group_id: int,
    username: str,
    me: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Владелец/админ может убрать любого. Участник может выйти сам (username == свой)."""
    my_membership = _require_member(db, group_id, me.id)
    target = db.query(models.User).filter_by(username=username.lstrip("@").lower()).first()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    is_self = target.id == me.id
    is_privileged = my_membership.role in (models.GroupRole.owner, models.GroupRole.admin)
    if not is_self and not is_privileged:
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    target_membership = _get_membership(db, group_id, target.id)
    if target_membership:
        if target_membership.role == models.GroupRole.owner and not is_self:
            raise HTTPException(status_code=403, detail="Нельзя удалить владельца группы")
        db.delete(target_membership)
        db.commit()
    return {"ok": True}


@router.patch("/{group_id}/members/{username}/role")
def change_role(
    group_id: int,
    username: str,
    role: models.GroupRole,
    me: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Только владелец группы может назначать/снимать админов."""
    my_membership = _require_member(db, group_id, me.id)
    if my_membership.role != models.GroupRole.owner:
        raise HTTPException(status_code=403, detail="Менять роли может только владелец группы")
    if role == models.GroupRole.owner:
        raise HTTPException(status_code=400, detail="Передача владения группой пока не поддержана")

    target = db.query(models.User).filter_by(username=username.lstrip("@").lower()).first()
    target_membership = target and _get_membership(db, group_id, target.id)
    if not target_membership:
        raise HTTPException(status_code=404, detail="Участник не найден")
    if target_membership.role == models.GroupRole.owner:
        raise HTTPException(status_code=400, detail="Нельзя менять роль владельца")

    target_membership.role = role
    db.commit()
    return {"ok": True}
