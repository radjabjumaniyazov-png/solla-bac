"""Мелкие хелперы, общие для нескольких роутеров."""
from sqlalchemy.orm import Session

from . import models


def direct_chat_id(user_a_id: int, user_b_id: int) -> int:
    """
    Детерминированный chat_id для личного чата: не зависит от того, кто кому
    написал первым, поэтому оба участника всегда попадают в один и тот же чат.
    Работает, пока id пользователей < 100_000_000 (для SQLite/Postgres serial
    этого хватит на очень долгое время).
    """
    lo, hi = sorted((user_a_id, user_b_id))
    return lo * 100_000_000 + hi


def is_blocked(db: Session, a_id: int, b_id: int) -> bool:
    """True, если a заблокировал b или b заблокировал a (в любую сторону)."""
    q = db.query(models.BlacklistEntry).filter(
        (
            (models.BlacklistEntry.owner_id == a_id)
            & (models.BlacklistEntry.blocked_user_id == b_id)
        )
        | (
            (models.BlacklistEntry.owner_id == b_id)
            & (models.BlacklistEntry.blocked_user_id == a_id)
        )
    )
    return db.query(q.exists()).scalar()
