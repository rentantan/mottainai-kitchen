"""Japan time: the app's dates (expiry, "today", monthly stats, daily quotas) follow Asia/Tokyo."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

JAPAN_TZ = ZoneInfo("Asia/Tokyo")


def now_japan() -> datetime:
    return datetime.now(JAPAN_TZ)


def now_japan_iso() -> str:
    return now_japan().isoformat()


def today_japan() -> date:
    return now_japan().date()
