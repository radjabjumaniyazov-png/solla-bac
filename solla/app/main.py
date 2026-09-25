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
from .routers import auth, contacts, profile

# На старте создаём таблицы, если их ещё нет. Для реальных миграций
# (когда схема начнёт меняться на проде) на это место позже встанет Alembic —
# create_all трогает только отсутствующие таблицы и не умеет менять существующие.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Solla API", version="0.1.0")

# CORS открыт полностью для разработки. Перед продом сузьте allow_origins
# до реального домена/схемы фронтенда.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(contacts.router)


@app.get("/")
def health():
    return {"status": "ok", "service": "solla-backend"}
