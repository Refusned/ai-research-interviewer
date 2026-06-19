import os

# Тестам реальный ключ не нужен — обращения к LLM всюду замоканы. Но Settings
# требует ключ на импорте (fail-fast в проде), поэтому подставляем заглушку.
os.environ.setdefault("OLLAMA_API_KEY", "test-key")

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Сбрасываем in-memory состояние лимитера, чтобы тесты не влияли друг на друга."""
    from app import ratelimit

    ratelimit._ip_hits.clear()
    ratelimit._global_hits.clear()
    yield
