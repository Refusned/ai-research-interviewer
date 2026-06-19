"""Тесты API. Реальных сетевых вызовов к Ollama нет — LLM замокан."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app import llm
from app.llm import LLMError, _parse
from app.main import app
from app.schemas import AskResponse

client = TestClient(app)


def test_shallow_answer_asks_clarifying(monkeypatch):
    async def fake(answer, history):
        return AskResponse(decision="clarify", reply="А что было решающим — цена или программа?")

    monkeypatch.setattr("app.main.ask_llm", fake)

    response = client.post("/api/ask", json={"answer": "не помню"})
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "clarify"
    assert body["reply"]


def test_detailed_answer_completes(monkeypatch):
    async def fake(answer, history):
        return AskResponse(decision="complete", reply="Спасибо за развёрнутый ответ!")

    monkeypatch.setattr("app.main.ask_llm", fake)

    response = client.post(
        "/api/ask",
        json={"answer": "Сравнил три курса по цене, программе и отзывам, выбрал по преподавателю."},
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "complete"


def test_llm_error_maps_to_502(monkeypatch):
    async def boom(answer, history):
        raise LLMError("Превышено время ожидания ответа модели")

    monkeypatch.setattr("app.main.ask_llm", boom)

    response = client.post("/api/ask", json={"answer": "любой ответ"})
    assert response.status_code == 502
    assert "detail" in response.json()


def test_parse_valid_json():
    result = _parse('{"decision": "complete", "reply": "Спасибо!"}')
    assert result.decision == "complete"
    assert result.reply == "Спасибо!"


def test_parse_json_in_markdown_fence():
    raw = 'Вот ответ:\n```json\n{"decision": "complete", "reply": "Спасибо!"}\n```'
    result = _parse(raw)
    assert result.decision == "complete"
    assert result.reply == "Спасибо!"


def test_parse_json_with_surrounding_text():
    raw = 'Спасибо!\n\n{"decision": "complete", "reply": "Спасибо за участие!"}'
    result = _parse(raw)
    assert result.decision == "complete"
    assert result.reply == "Спасибо за участие!"


def test_parse_two_objects_uses_first():
    result = _parse('{"decision": "clarify", "reply": "первый"} {"decision": "complete", "reply": "второй"}')
    assert result.decision == "clarify"
    assert result.reply == "первый"


def test_parse_object_with_trailing_text():
    result = _parse('{"decision": "complete", "reply": "готово"} и ещё какой-то текст }')
    assert result.decision == "complete"
    assert result.reply == "готово"


def test_parse_invalid_enum_falls_back():
    result = _parse('{"decision": "maybe", "reply": "x"}')
    assert result.decision == "clarify"  # невалидный enum → фоллбэк


def test_parse_missing_key_falls_back():
    result = _parse('{"decision": "complete"}')
    assert result.decision == "clarify"  # нет reply → фоллбэк


def test_parse_fallback_on_non_json():
    result = _parse("Это просто текст, а не JSON")
    assert result.decision == "clarify"
    assert result.reply == "Это просто текст, а не JSON"


def test_empty_answer_rejected():
    assert client.post("/api/ask", json={"answer": ""}).status_code == 422


def test_blank_answer_rejected():
    assert client.post("/api/ask", json={"answer": "    "}).status_code == 422


def test_oversized_history_rejected():
    huge_history = [{"role": "user", "content": "x"}] * 21
    response = client.post("/api/ask", json={"answer": "привет", "history": huge_history})
    assert response.status_code == 422


def test_rate_limit_returns_429(monkeypatch):
    async def fake(answer, history):
        return AskResponse(decision="clarify", reply="?")

    monkeypatch.setattr("app.main.ask_llm", fake)

    codes = [client.post("/api/ask", json={"answer": "ответ"}).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5  # первые 5 проходят
    assert 429 in codes[5:]        # дальше срабатывает лимит


# --- Прямое покрытие клиента ask_llm (без сети, через httpx-моки) ---

def test_ask_llm_parses_clean_response(monkeypatch):
    async def fake_post(self, url, **kwargs):
        return httpx.Response(
            200,
            json={"message": {"content": '{"decision": "complete", "reply": "Спасибо!"}'}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    result = asyncio.run(llm.ask_llm("подробный ответ", []))
    assert result.decision == "complete"
    assert result.reply == "Спасибо!"


def test_ask_llm_timeout_maps_to_llmerror(monkeypatch):
    async def fake_post(self, *args, **kwargs):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(LLMError):
        asyncio.run(llm.ask_llm("ответ", []))


def test_ask_llm_http_error_maps_to_llmerror(monkeypatch):
    async def fake_post(self, url, **kwargs):
        return httpx.Response(500, text="upstream boom", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(LLMError):
        asyncio.run(llm.ask_llm("ответ", []))


def test_ask_llm_empty_content_maps_to_llmerror(monkeypatch):
    async def fake_post(self, url, **kwargs):
        return httpx.Response(200, json={"message": {"content": "   "}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(LLMError):
        asyncio.run(llm.ask_llm("ответ", []))
