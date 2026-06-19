"""FastAPI-приложение: отдаёт фронтенд и принимает ответы респондентов."""

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse

from .llm import LLMError, ask_llm
from .ratelimit import rate_limit
from .schemas import AskRequest, AskResponse

app = FastAPI(title="Исследователь выбора онлайн-курсов")

# Абсолютный путь от расположения файла — не зависим от текущей директории запуска.
INDEX_HTML = Path(__file__).resolve().parent.parent / "static" / "index.html"


@app.get("/")
async def index() -> FileResponse:
    """Главная страница. FastAPI сам отдаёт фронт → один origin, без CORS."""
    return FileResponse(INDEX_HTML)


@app.post("/api/ask", response_model=AskResponse, dependencies=[Depends(rate_limit)])
async def ask(payload: AskRequest) -> AskResponse:
    """Передаёт ответ респондента исследователю-LLM и возвращает его реакцию."""
    try:
        return await ask_llm(payload.answer, payload.history)
    except LLMError as exc:
        # Наш «апстрим» (LLM) недоступен/ошибся → 502 Bad Gateway.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
