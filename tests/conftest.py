import os

# Тестам реальный ключ не нужен — обращения к LLM всюду замоканы. Но Settings
# требует ключ на импорте (fail-fast в проде), поэтому подставляем заглушку.
os.environ.setdefault("OLLAMA_API_KEY", "test-key")
