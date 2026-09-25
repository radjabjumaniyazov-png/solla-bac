"""
Реестр активных WebSocket-соединений.

Один пользователь может быть подключён с нескольких устройств одновременно
(телефон + веб), поэтому храним НЕ одно соединение на user_id, а список.

Это in-memory реализация — годится для одного инстанса сервера. Если позже
понадобится несколько инстансов за балансировщиком, это место придётся
заменить на Redis pub/sub (каждый инстанс подписывается на канал и
ретранслирует своим локальным соединениям) — сам API эндпоинтов при этом
не изменится.
"""
import json

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(user_id, []).append(ws)

    def disconnect(self, user_id: int, ws: WebSocket):
        conns = self._connections.get(user_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(user_id, None)

    def is_online(self, user_id: int) -> bool:
        return bool(self._connections.get(user_id))

    async def send_to_user(self, user_id: int, payload: dict):
        """Шлёт payload на все активные соединения этого пользователя.
        Молча ничего не делает, если пользователь оффлайн — сообщение уже
        сохранено в БД роутером до вызова этого метода, так что не потеряется."""
        for ws in list(self._connections.get(user_id, [])):
            try:
                await ws.send_text(json.dumps(payload, default=str))
            except Exception:  # noqa: BLE001 — сокет мог уже отвалиться
                self.disconnect(user_id, ws)

    async def send_to_users(self, user_ids: list[int], payload: dict):
        for uid in user_ids:
            await self.send_to_user(uid, payload)


manager = ConnectionManager()
