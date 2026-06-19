"""Лёгкий in-memory rate-limiting для публичного endpoint'а.

Защищает от абуза: каждый запрос к LLM стоит реальных денег, а `/api/ask`
открыт без авторизации. Один процесс uvicorn → состояние в памяти достаточно
(для нескольких воркеров понадобился бы Redis — вне рамок демо).
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

PER_IP_LIMIT = 5            # запросов с одного IP
PER_IP_WINDOW = 30.0       # за столько секунд
GLOBAL_DAILY_LIMIT = 500   # суточный предохранитель на весь сервис
_DAY = 86400.0

_ip_hits: dict[str, deque] = defaultdict(deque)
_global_hits: deque = deque()


def _client_ip(request: Request) -> str:
    # За одним доверенным reverse-proxy (Caddy) реальный адрес клиента — ПОСЛЕДНИЙ
    # в X-Forwarded-For: его дописывает сам Caddy. Первые значения клиент может
    # подделать, поэтому берём последний — спуфингом заголовка его не обойти.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    """FastAPI-зависимость: бросает 429 при превышении лимитов."""
    now = time.monotonic()

    # Глобальный суточный предохранитель.
    while _global_hits and now - _global_hits[0] > _DAY:
        _global_hits.popleft()
    if len(_global_hits) >= GLOBAL_DAILY_LIMIT:
        raise HTTPException(status_code=429, detail="Сервис временно перегружен. Попробуйте позже.")

    # Лимит на один IP (скользящее окно).
    hits = _ip_hits[_client_ip(request)]
    while hits and now - hits[0] > PER_IP_WINDOW:
        hits.popleft()
    if len(hits) >= PER_IP_LIMIT:
        raise HTTPException(status_code=429, detail="Слишком много запросов. Подождите немного.")

    hits.append(now)
    _global_hits.append(now)
