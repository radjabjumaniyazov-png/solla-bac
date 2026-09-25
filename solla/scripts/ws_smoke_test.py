"""
Ручная проверка WebSocket-чата на живом сервере (uvicorn app.main:app --reload).

Использование:
    pip install websockets requests
    python scripts/ws_smoke_test.py

Скрипт сам зарегистрирует двух пользователей (alice/bob), подключит обоих
по WebSocket, отправит сообщение от alice к bob и покажет, что bob получил
его мгновенно — то есть что доставка в реальном времени действительно
работает, а не только пишется в БД.
"""
import asyncio
import json

import requests
import websockets

BASE = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"


def register_and_login(login: str, username: str, password: str) -> str:
    requests.post(f"{BASE}/auth/register", json={
        "login": login, "username": username, "password": password,
    })  # 409, если уже существует — это нормально при повторном запуске
    r = requests.post(f"{BASE}/auth/login", json={"login": login, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


async def main():
    alice_token = register_and_login("alice_login", "alice_test", "password123")
    bob_token = register_and_login("bob_login", "bob_test", "password123")

    async with websockets.connect(f"{WS_BASE}/ws?token={alice_token}") as alice_ws, \
               websockets.connect(f"{WS_BASE}/ws?token={bob_token}") as bob_ws:

        await alice_ws.send(json.dumps({
            "chat_type": "direct", "to_username": "bob_test", "text": "Привет от Алисы!",
        }))

        # bob должен получить сообщение без опроса, сразу же
        incoming = await asyncio.wait_for(bob_ws.recv(), timeout=5)
        print("Bob получил:", incoming)

        # alice тоже получает копию (синхронизация между своими устройствами)
        own_copy = await asyncio.wait_for(alice_ws.recv(), timeout=5)
        print("Alice видит у себя:", own_copy)


if __name__ == "__main__":
    asyncio.run(main())
