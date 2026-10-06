"""Runtime configuration, read from environment variables (never baked into the image)."""

import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


API_KEY = os.environ.get("API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://legion1.di.uoa.gr/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "llama3.1")
LLM_TIMEOUT = _int("LLM_TIMEOUT", 60)
IDE_BACKEND_URL = os.environ.get("IDE_BACKEND_URL", "http://localhost:3001/api")

MAX_FILE_BYTES = _int("MAX_FILE_BYTES", 512_000)  # files larger than this are skipped by the analyzer
MAX_WORKSPACE_FILES = _int("MAX_WORKSPACE_FILES", 400)
MAX_SESSIONS = _int("MAX_SESSIONS", 500)
MAX_HISTORY_TURNS = _int("MAX_HISTORY_TURNS", 10)
