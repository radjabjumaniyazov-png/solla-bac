"""
Solla backend — точка входа.

Запуск локально:
    uvicorn app.main:app --reload

Документация (Swagger) появится на http://127.0.0.1:8000/docs — там можно
руками потыкать все эндпоинты без фронтенда, пока его нет.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import Base, engine
from .routers import auth, channels, contacts, groups, messages, profile

# На старте создаём таблицы, если их ещё нет. Для реальных миграций
# (когда схема начнёт меняться на проде) на это место позже встанет Alembic —
# create_all трогает только отсутствующие таблицы и не умеет менять существующие.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Solla API", version="0.1.0")

# CORS открыт для всех источников. allow_credentials=False — мы не используем
# куки (только Bearer-токен в заголовке Authorization), поэтому credentialed
# CORS не нужен. Важно: сочетание allow_origins=["*"] с allow_credentials=True
# запрещено спецификацией CORS — строгие браузерные движки (в т.ч. Chromium в
# Android WebView) могут из-за этого молча блокировать запрос ещё на этапе
# preflight, и с фронтенда это будет выглядеть как обычная сетевая ошибка.
# Перед реальным продом всё равно сузьте allow_origins до конкретного домена.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(contacts.router)
app.include_router(groups.router)
app.include_router(channels.router)
app.include_router(messages.router)


@app.get("/")
def health():
    return {"status": "ok", "service": "solla-backend"}
