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


def _json_objects(content: str):
    """Извлекает JSON-объекты из ответа модели — от строгого способа к мягкому.

    Поле `format` обычно даёт чистый JSON, но не каждая облачная модель жёстко
    его соблюдает: иногда JSON приходит обёрнутым в ```-блок или с текстом вокруг.
    """
    # 1) весь ответ — чистый JSON
    try:
        yield json.loads(content)
    except json.JSONDecodeError:
        pass
    # 2) JSON внутри markdown-блока ```json ... ```
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.S)
    if fence:
        try:
            yield json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    # 3) первый валидный объект, начиная с первой `{` (текст вокруг игнорируется)
    start = content.find("{")
    if start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(content[start:])
            yield obj
        except json.JSONDecodeError:
            pass


def _parse(content: str) -> AskResponse:
    """Разбирает structured output модели.

    Если ни один способ не дал валидный объект нужной формы — мягкий фоллбэк:
    показываем сырой текст как уточняющий вопрос (переспросить безопаснее,
    чем ошибочно завершить интервью).
    """
    for data in _json_objects(content):
        try:
            return AskResponse(decision=data["decision"], reply=data["reply"])
        except (KeyError, ValueError, TypeError):
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

    try:
        data = response.json()
    except ValueError as exc:  # тело ответа оказалось не JSON
        raise LLMError("Модель вернула некорректный ответ") from exc

    content = data.get("message", {}).get("content", "").strip()
    if not content:
        raise LLMError("Модель вернула пустой ответ")

    return _parse(content)
