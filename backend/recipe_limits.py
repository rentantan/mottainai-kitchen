"""Gemini call limits: per-account interval/hourly limits (in memory) and daily caps (SQLite)."""
from __future__ import annotations

import threading
import time

from clock import today_japan
from config import (MAX_REQUESTS_PER_DAY, MAX_REQUESTS_PER_DAY_PER_USER, MAX_REQUESTS_PER_HOUR_PER_USER,
                    MIN_REQUEST_INTERVAL_SECONDS)
from database import db_connection

# Per-account Gemini call times (in memory; the daily counts live in SQLite).
_request_history: dict[str, list[float]] = {}
_last_request_at: dict[str, float] = {}
# FastAPI runs sync handlers in a thread pool: without a lock, two quick taps can both pass
# the interval check before either records its call, and both reach Gemini.
rate_lock = threading.Lock()


def user_rate_limit_message(user_id: str) -> str | None:
    """Short-term per-account limits (interval and hourly). Read-only: nothing is recorded here.
    Call with rate_lock held, together with record_user_request."""
    now = time.time()
    if now - _last_request_at.get(user_id, 0.0) < MIN_REQUEST_INTERVAL_SECONDS:
        return f"AI提案は{int(MIN_REQUEST_INTERVAL_SECONDS)}秒以上あけて使ってください。少し待ってから再試行してください。"
    recent = [stamp for stamp in _request_history.get(user_id, []) if now - stamp < 3600]
    _request_history[user_id] = recent
    if len(recent) >= MAX_REQUESTS_PER_HOUR_PER_USER:
        return f"AI提案は1時間に{MAX_REQUESTS_PER_HOUR_PER_USER}回までです。時間をおいて再試行してください。"
    return None


def record_user_request(user_id: str) -> None:
    now = time.time()
    _last_request_at[user_id] = now
    _request_history.setdefault(user_id, []).append(now)


def forget_user_request(user_id: str) -> None:
    """A failed call does not count toward the hourly limit (the interval still applies)."""
    with rate_lock:
        history = _request_history.get(user_id)
        if history:
            history.pop()


def reserve_daily_request(user_id: str) -> str | None:
    """Count one Gemini call against the app-wide and per-account daily caps.

    Returns None when reserved, or the message to show when a cap is reached.
    BEGIN IMMEDIATE makes check-and-increment atomic across concurrent requests.
    Cache hits never reach this function.
    """
    today = today_japan().isoformat()
    with db_connection(immediate=True) as connection:
        row = connection.execute(
            "SELECT request_count FROM gemini_daily_usage WHERE usage_date = ?", (today,)
        ).fetchone()
        app_used = int(row["request_count"]) if row else 0
        row = connection.execute(
            "SELECT request_count FROM gemini_user_daily_usage WHERE user_id = ? AND usage_date = ?", (user_id, today)
        ).fetchone()
        user_used = int(row["request_count"]) if row else 0
        if user_used >= MAX_REQUESTS_PER_DAY_PER_USER:
            return f"AI提案は1人1日{MAX_REQUESTS_PER_DAY_PER_USER}回までです（本日{user_used}回使用）。明日また使えます。"
        if app_used >= MAX_REQUESTS_PER_DAY:
            return f"アプリ全体のAI提案が本日の上限（{MAX_REQUESTS_PER_DAY}回）に達しました。明日また使えます。"
        connection.execute(
            """
            INSERT INTO gemini_daily_usage (usage_date, request_count) VALUES (?, 1)
            ON CONFLICT(usage_date) DO UPDATE SET request_count = request_count + 1
            """,
            (today,),
        )
        connection.execute(
            """
            INSERT INTO gemini_user_daily_usage (user_id, usage_date, request_count) VALUES (?, ?, 1)
            ON CONFLICT(user_id, usage_date) DO UPDATE SET request_count = request_count + 1
            """,
            (user_id, today),
        )
    return None


def release_user_daily_request(user_id: str) -> None:
    """Give a failed call back to the account. The app-wide count is kept, because the
    provider may still have counted the attempt against the shared free quota."""
    with db_connection() as connection:
        connection.execute(
            "UPDATE gemini_user_daily_usage SET request_count = MAX(request_count - 1, 0) "
            "WHERE user_id = ? AND usage_date = ?",
            (user_id, today_japan().isoformat()),
        )
