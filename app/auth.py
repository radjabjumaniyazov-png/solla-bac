"""
Хеширование паролей (bcrypt) и выдача/проверка JWT-токенов.

SECRET_KEY обязательно переопределить в .env в проде — значение по умолчанию
годится только для локальной разработки и должно смениться перед деплоем.
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, WebSocket, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal, get_db

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me-before-deploy")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось подтвердить учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_error
    except JWTError:
        raise credentials_error

    user = db.get(models.User, int(user_id))
    if user is None:
        raise credentials_error
    return user


async def get_current_user_ws(websocket: WebSocket) -> models.User:
    """
    Аутентификация для WebSocket. Браузерный WebSocket API не умеет
    отправлять произвольные заголовки при установке соединения (в отличие
    от обычного fetch), поэтому токен передаётся как query-параметр:
    ws://host/ws?token=<JWT>. Это стандартная практика для WS-аутентификации.
    """
    token = websocket.query_params.get("token")
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    except JWTError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    # get_db() — обычный generator-dependency для HTTP-запросов, для WS его
    # неудобно переиспользовать через Depends, поэтому открываем сессию сами.
    db = SessionLocal()
    try:
        user = db.get(models.User, int(user_id))
    finally:
        db.close()
    if user is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return user
