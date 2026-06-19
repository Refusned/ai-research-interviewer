"""Контракты API и JSON-схема для structured output модели."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Decision = Literal["clarify", "complete"]


class Message(BaseModel):
    """Одна реплика диалога. Роли ограничены — подменить `system` нельзя."""

    role: Literal["user", "assistant"]
    content: str


class AskRequest(BaseModel):
    answer: str = Field(..., min_length=1, max_length=4000)
    history: list[Message] = Field(default_factory=list)

    @field_validator("answer")
    @classmethod
    def answer_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Ответ не может состоять из одних пробелов")
        return value


class AskResponse(BaseModel):
    decision: Decision
    reply: str


# JSON Schema, которую отдаём Ollama в поле `format`. Совпадает по форме с
# AskResponse — единый контракт «модель ↔ API ↔ фронтенд».
LLM_FORMAT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["clarify", "complete"]},
        "reply": {"type": "string"},
    },
    "required": ["decision", "reply"],
}
