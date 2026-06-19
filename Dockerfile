FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

# Запуск от непривилегированного пользователя
RUN useradd --system --no-create-home appuser
USER appuser

EXPOSE 8000

# Ключ передаётся через окружение: docker run -e OLLAMA_API_KEY=... -e OLLAMA_MODEL=...
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
