"""
Подключение к базе данных.

Сейчас — SQLite (файл solla.db рядом с проектом). Когда придёт время
переезжать на PostgreSQL, достаточно поменять DATABASE_URL в .env на
postgresql://user:pass@host/dbname — весь остальной код (модели, запросы)
не изменится, потому что мы используем SQLAlchemy ORM, а не сырой SQL.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./solla.db")

# check_same_thread нужен только для SQLite: разрешаем работу из разных потоков,
# т.к. FastAPI обрабатывает запросы асинхронно.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency для FastAPI: открывает сессию на запрос и закрывает после."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
