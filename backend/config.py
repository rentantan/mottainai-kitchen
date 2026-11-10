from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

APP_VERSION = "2.3.0"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "45"))
CACHE_SECONDS = int(os.getenv("RECIPE_CACHE_SECONDS", str(24 * 60 * 60)))
MAX_REQUESTS_PER_HOUR_PER_IP = int(os.getenv("GEMINI_MAX_REQUESTS_PER_HOUR_PER_IP", "5"))
MAX_REQUESTS_PER_DAY = int(os.getenv("GEMINI_MAX_REQUESTS_PER_DAY", "8"))
MIN_REQUEST_INTERVAL_SECONDS = float(os.getenv("GEMINI_MIN_REQUEST_INTERVAL_SECONDS", "20"))
PROMPT_VERSION = "student-recipe-v3"
DATABASE_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).resolve().parent / "data" / "mottainai.db"))
