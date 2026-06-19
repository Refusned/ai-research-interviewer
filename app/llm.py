"""Асинхронный клиент Ollama Cloud."""

import json
import logging
import re

import httpx

from .config import settings
from .prompt import SYSTEM_PROMPT
from .schemas import LLM_FORMAT_SCHEMA, AskResponse, Message

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Ошибка обращения к LLM. На уровне роутера маппится в HTTP 502."""


def _build_messages(answer: str, history: list[Message]) -> list[dict]:
    """Системный промпт всегда добавляется на сервере, поверх истории клиента."""
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": answer})
    return messages


def _parse(content: str) -> AskResponse:
    """Разбирает structured output модели.

    Поле `format` обычно даёт чистый JSON, но не каждая облачная модель жёстко
    его соблюдает: иногда JSON приходит обёрнутым в ```-блок или с текстом
    вокруг. Поэтому пробуем несколько способов извлечь объект. Если всё мимо —
    мягкий фоллбэк: показываем сырой текст как уточняющий вопрос (переспросить
    безопаснее, чем ошибочно завершить интервью).
    """
    candidates = [content]
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.S)
    if fence:
        candidates.append(fence.group(1))
    braces = re.search(r"\{.*\}", content, re.S)
    if braces:
        candidates.append(braces.group(0))

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            return AskResponse(decision=data["decision"], reply=data["reply"])
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue

    logger.warning("Structured output не распознан, использую сырой текст")
    return AskResponse(decision="clarify", reply=content)


async def ask_llm(answer: str, history: list[Message]) -> AskResponse:
    """Отправляет ответ респондента в Ollama Cloud и возвращает реакцию исследователя."""
    payload = {
        "model": settings.ollama_model,
        "messages": _build_messages(answer, history),
        "stream": False,
        "think": False,  # отключаем reasoning: чистый JSON в content + меньше задержка
        "format": LLM_FORMAT_SCHEMA,
        "options": {"temperature": 0.3},  # низкая t — стабильная классификация
    }
    headers = {"Authorization": f"Bearer {settings.ollama_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise LLMError("Превышено время ожидания ответа модели") from exc
    except httpx.HTTPStatusError as exc:
        raise LLMError(f"Модель вернула ошибку {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise LLMError("Не удалось обратиться к модели") from exc

    content = response.json().get("message", {}).get("content", "").strip()
    if not content:
        raise LLMError("Модель вернула пустой ответ")

    return _parse(content)
