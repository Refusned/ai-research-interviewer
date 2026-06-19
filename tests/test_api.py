"""Тесты API. Реальных сетевых вызовов к Ollama нет — LLM замокан."""

from fastapi.testclient import TestClient

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


def test_parse_fallback_on_non_json():
    result = _parse("Это просто текст, а не JSON")
    assert result.decision == "clarify"
    assert result.reply == "Это просто текст, а не JSON"


def test_empty_answer_rejected():
    assert client.post("/api/ask", json={"answer": ""}).status_code == 422


def test_blank_answer_rejected():
    assert client.post("/api/ask", json={"answer": "    "}).status_code == 422
