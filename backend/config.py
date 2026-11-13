from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

APP_VERSION = "2.5.0"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "25"))
# Upper bound for one suggestion request including 503 retries. Keep this below the
# frontend timeout (FRONTEND_TIMEOUT in frontend/src/api.ts, 60s) so the browser never
# gives up while the backend is still spending quota.
GEMINI_TOTAL_DEADLINE_SECONDS = float(os.getenv("GEMINI_TOTAL_DEADLINE_SECONDS", "45"))
CACHE_SECONDS = int(os.getenv("RECIPE_CACHE_SECONDS", str(24 * 60 * 60)))
# App-wide daily cap (protects the shared free quota) plus per-account limits, so one
# account cannot use up the day's calls for everyone. The old *_PER_IP name is still read.
MAX_REQUESTS_PER_DAY = int(os.getenv("GEMINI_MAX_REQUESTS_PER_DAY", "8"))
MAX_REQUESTS_PER_DAY_PER_USER = int(os.getenv("GEMINI_MAX_REQUESTS_PER_DAY_PER_USER", "4"))
MAX_REQUESTS_PER_HOUR_PER_USER = int(os.getenv(
    "GEMINI_MAX_REQUESTS_PER_HOUR_PER_USER", os.getenv("GEMINI_MAX_REQUESTS_PER_HOUR_PER_IP", "3")))
MIN_REQUEST_INTERVAL_SECONDS = float(os.getenv("GEMINI_MIN_REQUEST_INTERVAL_SECONDS", "20"))
PROMPT_VERSION = "student-recipe-v8"  # bump when prompt or ingredient matching changes (invalidates cache)
_BACKEND_DIR = Path(__file__).resolve().parent


def _database_path() -> str:
    """A relative DATABASE_PATH is taken from the backend folder, not from wherever uvicorn
    was started, so the same .env always points at the same file."""
    raw = os.getenv("DATABASE_PATH", "").strip()
    if not raw:
        return str(_BACKEND_DIR / "data" / "mottainai.db")
    if raw == ":memory:" or Path(raw).is_absolute():
        return raw
    return str(_BACKEND_DIR / raw)


DATABASE_PATH = _database_path()
