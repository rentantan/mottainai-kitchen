from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    str(Path(__file__).resolve().parent / "data" / "mottainai.db"),
)

app = FastAPI(
    title="Mottainai Kitchen API",
    description="大学生の一人暮らし向け・節約時短レシピ提案API（Gemini API対応）",
    version=APP_VERSION,
)

origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


class PantryInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    quantity: float = Field(gt=0, le=100000)
    unit: str = Field(default="個", max_length=20)
    expiry_date: date
    category: str = Field(default="その他", max_length=30)


class PantryItemWrite(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    quantity: float = Field(gt=0, le=100000)
    unit: str = Field(default="個", max_length=20)
    expiryDate: date
    category: str = Field(default="その他", max_length=30)
    emoji: str = Field(default="🛒", max_length=8)
    note: str = Field(default="", max_length=300)


class RecipePreferences(BaseModel):
    budget_yen: Literal[300, 500, 700] = 500
    max_minutes: Literal[10, 20, 30] = 20


class SuggestRequest(BaseModel):
    pantry: list[PantryInput] = Field(default_factory=list, max_length=200)
    preferences: RecipePreferences = Field(default_factory=RecipePreferences)
    refresh_nonce: int = Field(default=0, ge=0, le=1_000_000_000)


class AuthCredentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class AuthSession(BaseModel):
    token: str
    email: str


# Fallback recipes keep the core app usable when the API key is not configured,
# the free quota is temporarily exhausted, or the network is unavailable.
FALLBACK_RECIPES: list[dict[str, Any]] = [
    {
        "id": "egg-fried-rice",
        "name": "卵だけでも満足チャーハン",
        "description": "ごはんと卵があれば作れる、洗い物少なめの定番ごはん。",
        "minutes": 8,
        "difficulty": "かんたん",
        "emoji": "🍳",
        "ingredients": ["ごはん", "卵", "しょうゆ"],
        "ingredientDetails": ["ごはん 茶碗1杯", "卵 1個", "しょうゆ 小さじ1"],
        "steps": [
            "卵を溶き、フライパンに油をひいて卵に火が通るまで炒める。",
            "ごはんを加えてほぐしながら炒める。",
            "しょうゆを鍋肌から回し入れて全体を混ぜる。",
        ],
        "estimatedCostYen": 100,
    },
    {
        "id": "tofu-don",
        "name": "豆腐のそぼろ風どんぶり",
        "description": "ひき肉なしでもボリュームが出る、節約向けの一皿。",
        "minutes": 12,
        "difficulty": "かんたん",
        "emoji": "🍚",
        "ingredients": ["ごはん", "豆腐", "しょうゆ", "砂糖"],
        "ingredientDetails": ["ごはん 茶碗1杯", "豆腐 1/2丁", "しょうゆ 大さじ1", "砂糖 小さじ1"],
        "steps": [
            "豆腐はキッチンペーパーで軽く水気を取る。",
            "フライパンで豆腐を崩しながら炒め、水分を飛ばす。",
            "しょうゆと砂糖を加えてなじませ、ごはんにのせる。",
        ],
        "estimatedCostYen": 150,
    },
    {
        "id": "cabbage-egg",
        "name": "キャベツと卵のふんわり炒め",
        "description": "余り野菜を使い切りやすい、フライパンひとつの簡単おかず。",
        "minutes": 10,
        "difficulty": "かんたん",
        "emoji": "🥬",
        "ingredients": ["キャベツ", "卵", "塩こしょう"],
        "ingredientDetails": ["キャベツ 2枚", "卵 1個", "塩こしょう 少々"],
        "steps": [
            "キャベツを食べやすい大きさにちぎる。",
            "フライパンでキャベツを炒め、しんなりしたら溶き卵を加える。",
            "卵にしっかり火が通るまで混ぜ、塩こしょうで味を調える。",
        ],
        "estimatedCostYen": 120,
    },
    {
        "id": "butter-soy-pasta",
        "name": "きのこのバターしょうゆパスタ",
        "description": "パスタときのこで作る、材料少なめの一人ごはん。",
        "minutes": 15,
        "difficulty": "かんたん",
        "emoji": "🍝",
        "ingredients": ["パスタ", "しめじ", "しょうゆ", "バター"],
        "ingredientDetails": ["パスタ 80g", "しめじ 1/3パック", "しょうゆ 小さじ2", "バター 5g"],
        "steps": [
            "パスタを袋の表示どおりにゆでる。",
            "フライパンでしめじを炒め、ゆでたパスタを加える。",
            "しょうゆとバターを加えて全体を混ぜる。",
        ],
        "estimatedCostYen": 220,
    },
    {
        "id": "tuna-mayo-rice",
        "name": "ツナマヨたまご丼",
        "description": "火を使う工程を少なくしたい日に。ツナ缶を活用。",
        "minutes": 7,
        "difficulty": "かんたん",
        "emoji": "🥫",
        "ingredients": ["ごはん", "ツナ缶", "卵", "マヨネーズ"],
        "ingredientDetails": ["ごはん 茶碗1杯", "ツナ缶 1/2缶", "卵 1個", "マヨネーズ 小さじ1"],
        "steps": [
            "ツナ缶の油を軽く切り、マヨネーズと混ぜる。",
            "卵は黄身と白身にしっかり火が通るまで加熱する。",
            "ごはんにツナマヨと卵をのせる。",
        ],
        "estimatedCostYen": 230,
    },
]


RECIPE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "recipes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "minutes": {"type": "integer"},
                    "difficulty": {"type": "string", "enum": ["かんたん", "ふつう"]},
                    "emoji": {"type": "string"},
                    "ingredients": {"type": "array", "items": {"type": "string"}},
                    "ingredientDetails": {"type": "array", "items": {"type": "string"}},
                    "steps": {"type": "array", "items": {"type": "string"}},
                    "estimatedCostYen": {"type": "integer"},
                },
                "required": [
                    "name", "description", "minutes", "difficulty", "emoji",
                    "ingredients", "ingredientDetails", "steps", "estimatedCostYen",
                ],
            },
        }
    },
    "required": ["recipes"],
}


_suggestion_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_request_history: dict[str, list[float]] = {}
_last_request_at: dict[str, float] = {}


@contextmanager
def db_connection():
    """Open a short-lived SQLite connection and commit successful writes."""
    db_path = Path(DATABASE_PATH)
    if str(DATABASE_PATH) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DATABASE_PATH), timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database() -> None:
    with db_connection() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at REAL NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS pantry_items (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                quantity REAL NOT NULL CHECK(quantity > 0), unit TEXT NOT NULL,
                expiry_date TEXT NOT NULL, category TEXT NOT NULL, emoji TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                user_id TEXT REFERENCES users(id)
            )"""
        )
        pantry_columns = {row["name"] for row in connection.execute("PRAGMA table_info(pantry_items)")}
        if "user_id" not in pantry_columns:
            connection.execute("ALTER TABLE pantry_items ADD COLUMN user_id TEXT REFERENCES users(id)")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS app_state (
                id INTEGER PRIMARY KEY,
                consumed_count INTEGER NOT NULL DEFAULT 0,
                initialized INTEGER NOT NULL DEFAULT 0,
                user_id TEXT REFERENCES users(id)
            )"""
        )
        state_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'app_state'"
        ).fetchone()["sql"] or ""
        if "CHECK(id = 1)" in state_schema:
            connection.execute("ALTER TABLE app_state RENAME TO app_state_legacy")
            connection.execute(
                """CREATE TABLE app_state (
                    id INTEGER PRIMARY KEY,
                    consumed_count INTEGER NOT NULL DEFAULT 0,
                    initialized INTEGER NOT NULL DEFAULT 0,
                    user_id TEXT REFERENCES users(id)
                )"""
            )
            connection.execute(
                "INSERT INTO app_state (id, consumed_count, initialized, user_id) "
                "SELECT id, consumed_count, initialized, NULL FROM app_state_legacy"
            )
            connection.execute("DROP TABLE app_state_legacy")
        state_columns = {row["name"] for row in connection.execute("PRAGMA table_info(app_state)")}
        if "user_id" not in state_columns:
            connection.execute("ALTER TABLE app_state ADD COLUMN user_id TEXT REFERENCES users(id)")
        connection.execute("INSERT OR IGNORE INTO app_state (id, consumed_count, initialized, user_id) VALUES (1, 0, 0, NULL)")
        connection.execute(
            "DELETE FROM app_state WHERE user_id IS NOT NULL AND id NOT IN "
            "(SELECT MIN(id) FROM app_state WHERE user_id IS NOT NULL GROUP BY user_id)"
        )
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_app_state_user_id ON app_state(user_id) WHERE user_id IS NOT NULL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recipe_suggestion_cache (
                cache_key TEXT PRIMARY KEY,
                user_id TEXT REFERENCES users(id),
                result_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        cache_columns = {row["name"] for row in connection.execute("PRAGMA table_info(recipe_suggestion_cache)")}
        if "user_id" not in cache_columns:
            connection.execute("ALTER TABLE recipe_suggestion_cache ADD COLUMN user_id TEXT REFERENCES users(id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pantry_items_user_id ON pantry_items(user_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_recipe_cache_user_id ON recipe_suggestion_cache(user_id)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS gemini_daily_usage (
                usage_date TEXT PRIMARY KEY,
                request_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )


def _db_item_to_api(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "quantity": row["quantity"],
        "unit": row["unit"],
        "expiryDate": row["expiry_date"],
        "category": row["category"],
        "emoji": row["emoji"],
        "note": row["note"],
        "createdAt": row["created_at"],
    }


def _read_pantry_state(connection: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    rows = connection.execute(
        "SELECT * FROM pantry_items WHERE user_id = ? ORDER BY expiry_date ASC, created_at DESC", (user_id,)
    ).fetchall()
    state = connection.execute(
        "SELECT consumed_count, initialized FROM app_state WHERE user_id = ?", (user_id,)
    ).fetchone()
    return {
        "items": [_db_item_to_api(row) for row in rows],
        "consumedCount": int(state["consumed_count"] if state else 0),
        "initialized": bool(state["initialized"] if state else False),
    }


def _insert_pantry_item(connection: sqlite3.Connection, item: PantryItemWrite, user_id: str) -> dict[str, Any]:
    item_id = str(uuid.uuid4())
    created_at = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()
    connection.execute(
        """INSERT INTO pantry_items
           (id, name, quantity, unit, expiry_date, category, emoji, note, created_at, user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (item_id, item.name.strip(), item.quantity, item.unit, item.expiryDate.isoformat(),
         item.category, item.emoji, item.note, created_at, user_id),
    )
    connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user_id,))
    row = connection.execute("SELECT * FROM pantry_items WHERE id = ?", (item_id,)).fetchone()
    return _db_item_to_api(row)


# Create the local database automatically. No database server or paid service is needed.
init_database()


def _password_hash(password: str, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), actual_salt, 210_000)
    return f"{actual_salt.hex()}:{digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split(":", 1)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 210_000)
        return hmac.compare_digest(expected.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _current_user(request: Request) -> sqlite3.Row:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="ログインが必要です")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT users.id, users.email FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ? AND auth_sessions.expires_at > ?
            """,
            (_token_hash(token), time.time()),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="ログインの有効期限が切れています")
    return row


def _ensure_user_state(connection: sqlite3.Connection, user_id: str) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO app_state (id, consumed_count, initialized, user_id) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM app_state), 0, 0, ?)",
        (user_id,),
    )


def today_japan() -> date:
    return datetime.now(ZoneInfo("Asia/Tokyo")).date()


def normalize(value: str) -> str:
    return re.sub(r"[\s　]", "", value).lower()


def matches_ingredient(required: str, pantry_item: PantryInput) -> bool:
    required_n = normalize(required)
    pantry_n = normalize(pantry_item.name)
    if not required_n or not pantry_n:
        return False
    return required_n in pantry_n or pantry_n in required_n


def expiry_priority_points(days_left: int) -> int:
    """Deterministic priority: nearest non-expired dates receive the most points."""
    if days_left < 0:
        return 0
    if days_left == 0:
        return 100
    if days_left == 1:
        return 80
    if days_left == 2:
        return 60
    if days_left == 3:
        return 40
    if days_left == 4:
        return 20
    if days_left == 5:
        return 15
    if days_left == 6:
        return 10
    if days_left == 7:
        return 5
    return 0


def _expiry_context(item: PantryInput, today: date) -> dict[str, Any]:
    days_left = (item.expiry_date - today).days
    if days_left < 0:
        status = f"期限を{abs(days_left)}日過ぎている（この食材はレシピに使わない）"
    elif days_left == 0:
        status = "期限は今日"
    elif days_left <= 3:
        status = f"期限まであと{days_left}日（優先して使う）"
    else:
        status = f"期限まであと{days_left}日"
    return {
        "name": item.name,
        "quantity": item.quantity,
        "unit": item.unit,
        "category": item.category,
        "expiry_date": item.expiry_date.isoformat(),
        "expiry_status": status,
        "days_until_expiry": days_left,
    }


def _build_prompt(request: SuggestRequest) -> str:
    today = today_japan()
    pantry_context = [_expiry_context(item, today) for item in request.pantry]
    usable = [row for row in pantry_context if row["days_until_expiry"] >= 0]
    expired = [row for row in pantry_context if row["days_until_expiry"] < 0]
    prefs = request.preferences

    return f"""あなたは、日本の大学生の一人暮らしを助ける節約料理アドバイザーです。
今日の日付は {today.isoformat()} です。

【利用者像・必須条件】
- 大学生の一人暮らし。料理初心者でも作れる内容にする。
- 必ず1人分（servings=1）を想定する。
- 1食の食材費の目安は税込・概算で {prefs.budget_yen} 円以内を目指す。高価な食材は使わない。
- 調理時間は準備と加熱を含めて {prefs.max_minutes} 分以内を目指す。
- フライパン、鍋、電子レンジ程度で作れる。一口コンロや狭いキッチンでも作りやすく、特殊な調理器具は使わない。
- 洗い物が少なく、スーパーやコンビニで少量を買いやすい食材を優先する。
- 調味料を大量に買いそろえなくてよいレシピにする。
- ごはん、卵、豆腐、もやし、納豆、冷凍野菜、ツナ缶、パスタ、うどん等の安価な食材を活用する。

【登録されている食材】
{json.dumps(usable, ensure_ascii=False)}

【期限切れのため使ってはいけない食材】
{json.dumps(expired, ensure_ascii=False)}

【レシピ作成ルール】
1. 3つの異なるレシピを提案する。登録済み食材を優先し、期限が最も近いものを使えるレシピを上位候補にする。
2. 期限の優先順位は「今日まで > あと1日 > あと2日 > あと3日 > あと4〜7日 > 8日以上」。期限が今日〜3日以内の食材がある場合、可能な限りその食材を使う。
3. 期限切れの食材は絶対に材料に含めない。期限切れ食材を新しく買い足すような提案も避ける。
4. 買い足し材料はできるだけ少なくし、登録食材以外は原則2種類以内。調味料は一般的なものを優先する。
5. 食材名は照合しやすい短い名前（例「卵」「キャベツ」）にし、ingredientDetailsには1人分の分量（例「卵 1個」）を書く。
6. 手順は初心者向けに具体的な日本語で3〜6ステップにする。
7. 肉・魚・卵を使う場合は中心まで十分に加熱する手順にする。生食を前提にしない。
7. estimatedCostYenは1人分の材料費の概算整数。正確な販売価格ではないので現実的な目安にする。
8. 予算や時間を守れないレシピは作らない。3案は主食・丼・麺・おかず等でなるべく変化をつける。
9. 説明文や手順にMarkdown、コードブロック、JSON以外の前置きを含めない。

JSONスキーマに従って、recipes配列だけを返してください。"""


def _gemini_generate(prompt: str) -> dict[str, Any]:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY が設定されていません")

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.65,
            "maxOutputTokens": 3000,
            "responseMimeType": "application/json",
            "responseJsonSchema": RECIPE_RESPONSE_SCHEMA,
        },
    }
    request = UrlRequest(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
            "Accept": "application/json",
        },
        method="POST",
    )
    # Google recommends exponential backoff for transient 503 UNAVAILABLE errors.
    # Retry three times (up to four total attempts) before falling back to local recipes.
    max_503_retries = 3
    for attempt in range(max_503_retries + 1):
        try:
            with urlopen(request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as exc:
            # Do not return the raw provider response or request headers (which may contain secrets).
            if exc.code == 503 and attempt < max_503_retries:
                retry_after = None
                try:
                    retry_after = float(exc.headers.get("Retry-After", "")) if exc.headers else None
                except (TypeError, ValueError):
                    pass
                # Respect Retry-After when supplied; otherwise use 1s, 2s, 4s + jitter.
                delay = min(max(retry_after, 0.0), 10.0) if retry_after is not None else min(2 ** attempt, 4) + random.uniform(0.0, 0.35)
                time.sleep(delay)
                continue
            if exc.code == 503:
                raise RuntimeError(
                    "Gemini APIが一時的に混雑しています。自動で3回再試行しましたが接続できませんでした。少し時間をおいてしばらく待ってからもう一度提案してください。"
                ) from exc
            if exc.code == 429:
                provider_message = ""
                quota_labels: list[str] = []
                try:
                    body = json.loads(exc.read().decode("utf-8", errors="replace"))
                    error_obj = body.get("error", {}) if isinstance(body, dict) else {}
                    provider_message = str(error_obj.get("message", ""))[:800]
                    for detail in error_obj.get("details", []) if isinstance(error_obj, dict) else []:
                        if not isinstance(detail, dict):
                            continue
                        for violation in detail.get("violations", []) if isinstance(detail.get("violations"), list) else []:
                            if isinstance(violation, dict):
                                value = " ".join(str(violation.get(key, "")) for key in ("quotaId", "quotaMetric", "description"))
                                if value.strip():
                                    quota_labels.append(value[:300])
                except (ValueError, UnicodeDecodeError, AttributeError):
                    pass
                diagnostic = (provider_message + " " + " ".join(quota_labels)).lower()
                if any(term in diagnostic for term in ("perday", "per_day", "requests per day", "daily")):
                    message = "Gemini APIの日次リクエスト上限に達しています。日本時間17時以降（太平洋時間0時のリセット後）に再試行してください。"
                elif any(term in diagnostic for term in ("perminute", "per_minute", "requests per minute", "rpm")):
                    message = "Gemini APIの1分あたりのリクエスト上限に達しています。1分ほど待ってから再試行してください。"
                else:
                    message = "Gemini APIの無料利用上限（429 RESOURCE_EXHAUSTED）に達しました。AI StudioでこのモデルのRPM・TPM・RPDを確認してください。"
                raise RuntimeError(message) from exc
            if exc.code == 404:
                raise RuntimeError(f"Geminiモデル '{GEMINI_MODEL}' が見つかりません。backend/.env の GEMINI_MODEL を確認してください。") from exc
            if exc.code in (400, 401, 403):
                raise RuntimeError("Gemini APIのキー・モデル権限・リクエスト形式を確認してください。") from exc
            raise RuntimeError(f"Gemini APIでエラーが発生しました（HTTP {exc.code}）。") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("Gemini APIに接続できませんでした。ネットワークを確認してください。") from exc
    else:  # pragma: no cover - defensive guard; the loop exits via break or exception.
        raise RuntimeError("Gemini APIから応答を取得できませんでした。")

    try:
        parts = data["candidates"][0]["content"]["parts"]
        text_parts = [part.get("text", "") for part in parts if isinstance(part, dict)]
        content = "".join(text_parts).strip()
        if not content:
            raise ValueError("empty response")
        decoded = json.loads(content)
        if not isinstance(decoded, dict) or not isinstance(decoded.get("recipes"), list):
            raise ValueError("unexpected response shape")
        return decoded
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Gemini APIの応答をレシピデータとして読み取れませんでした。") from exc


def _safe_string(value: Any, fallback: str, limit: int = 160) -> str:
    if not isinstance(value, str):
        return fallback
    cleaned = value.strip()
    return cleaned[:limit] if cleaned else fallback


def _format_gemini_recipes(raw: dict[str, Any], pantry: list[PantryInput]) -> list[dict[str, Any]]:
    today = today_japan()
    formatted: list[dict[str, Any]] = []
    raw_recipes = raw.get("recipes", [])

    for index, candidate in enumerate(raw_recipes[:3]):
        if not isinstance(candidate, dict):
            continue
        raw_ingredients = candidate.get("ingredients", [])
        ingredients = list(dict.fromkeys(
            str(value).strip()[:50]
            for value in raw_ingredients
            if isinstance(value, str) and value.strip()
        ))[:12] if isinstance(raw_ingredients, list) else []
        if not ingredients:
            continue

        details_raw = candidate.get("ingredientDetails", [])
        details = [str(value).strip()[:80] for value in details_raw if isinstance(value, str) and value.strip()] if isinstance(details_raw, list) else []
        if len(details) != len(ingredients):
            details = ingredients.copy()

        steps_raw = candidate.get("steps", [])
        steps = [str(value).strip()[:240] for value in steps_raw if isinstance(value, str) and value.strip()] if isinstance(steps_raw, list) else []
        if not steps:
            continue

        # Only non-expired pantry items count as available or as expiry-priority ingredients.
        usable_pantry = [item for item in pantry if item.expiry_date >= today]
        expired_pantry = [item for item in pantry if item.expiry_date < today]
        # Reject a suggestion that appears to use an expired pantry item, unless another
        # non-expired stock of the same ingredient is available.
        uses_expired_stock = any(
            any(matches_ingredient(ingredient, expired_item) for expired_item in expired_pantry)
            and not any(matches_ingredient(ingredient, good_item) for good_item in usable_pantry)
            for ingredient in ingredients
        )
        if uses_expired_stock:
            continue
        matched = [ingredient for ingredient in ingredients if any(matches_ingredient(ingredient, item) for item in usable_pantry)]
        missing = [ingredient for ingredient in ingredients if ingredient not in matched]
        matched_items = [
            item for item in usable_pantry
            if any(matches_ingredient(ingredient, item) for ingredient in matched)
        ]
        expiry_days = [(item.expiry_date - today).days for item in matched_items]
        nearest_expiry_days = min(expiry_days, default=999)
        expiry_priority_score = sum(expiry_priority_points(days) for days in expiry_days)
        expiring_names = {
            item.name for item in matched_items
            if 0 <= (item.expiry_date - today).days <= 3
        }

        try:
            minutes = max(1, min(90, int(candidate.get("minutes", 15))))
        except (TypeError, ValueError):
            minutes = 15
        try:
            estimated_cost = max(0, min(5000, int(candidate.get("estimatedCostYen", 300))))
        except (TypeError, ValueError):
            estimated_cost = 300

        formatted.append({
            "id": f"gemini-{index}-{hashlib.sha1(_safe_string(candidate.get('name'), 'recipe').encode()).hexdigest()[:8]}",
            "name": _safe_string(candidate.get("name"), "節約かんたんごはん", 60),
            "description": _safe_string(candidate.get("description"), "冷蔵庫の食材で作れる一品です。", 180),
            "minutes": minutes,
            "difficulty": candidate.get("difficulty") if candidate.get("difficulty") in ("かんたん", "ふつう") else "かんたん",
            "emoji": _safe_string(candidate.get("emoji"), "🍚", 8),
            "ingredients": ingredients,
            "ingredientDetails": details,
            "steps": steps[:8],
            "matchedIngredients": matched,
            "missingIngredients": missing,
            "usesExpiring": len(expiring_names),
            "nearestExpiryDays": nearest_expiry_days,
            "expiryPriorityScore": expiry_priority_score,
            "matchPercent": round(len(matched) / max(1, len(ingredients)) * 100),
            "estimatedCostYen": estimated_cost,
            "servings": 1,
            "source": "Gemini AI",
        })
    formatted.sort(key=lambda row: (row["nearestExpiryDays"], -row["expiryPriorityScore"], -row["usesExpiring"], -row["matchPercent"], row["estimatedCostYen"], row["minutes"]))
    return formatted


def _format_fallback(pantry: list[PantryInput], preferences: RecipePreferences) -> list[dict[str, Any]]:
    today = today_japan()
    recipes: list[dict[str, Any]] = []
    for recipe in FALLBACK_RECIPES:
        if recipe["minutes"] > preferences.max_minutes:
            continue
        if recipe["estimatedCostYen"] > preferences.budget_yen:
            continue
        usable_pantry = [item for item in pantry if item.expiry_date >= today]
        matched = [ingredient for ingredient in recipe["ingredients"] if any(matches_ingredient(ingredient, item) for item in usable_pantry)]
        missing = [ingredient for ingredient in recipe["ingredients"] if ingredient not in matched]
        matched_items = [item for item in usable_pantry if any(matches_ingredient(ingredient, item) for ingredient in matched)]
        expiry_days = [(item.expiry_date - today).days for item in matched_items]
        nearest_expiry_days = min(expiry_days, default=999)
        priority_score = sum(expiry_priority_points(days) for days in expiry_days)
        expiring = {
            item.name for item in matched_items
            if 0 <= (item.expiry_date - today).days <= 3
        }
        recipes.append({
            **recipe,
            "matchedIngredients": matched,
            "missingIngredients": missing,
            "usesExpiring": len(expiring),
            "nearestExpiryDays": nearest_expiry_days,
            "expiryPriorityScore": priority_score,
            "matchPercent": round(len(matched) / max(1, len(recipe["ingredients"])) * 100),
            "servings": 1,
            "source": "アプリ内レシピ",
        })
    recipes.sort(key=lambda row: (row["nearestExpiryDays"], -row["expiryPriorityScore"], -row["usesExpiring"], -row["matchPercent"], row["estimatedCostYen"], row["minutes"]))
    return recipes[:3]


def _check_request_limit(client_ip: str) -> bool:
    now = time.time()
    last = _last_request_at.get(client_ip, 0.0)
    if now - last < MIN_REQUEST_INTERVAL_SECONDS:
        return False
    recent = [timestamp for timestamp in _request_history.get(client_ip, []) if now - timestamp < 3600]
    if len(recent) >= MAX_REQUESTS_PER_HOUR_PER_IP:
        return False
    recent.append(now)
    _request_history[client_ip] = recent
    _last_request_at[client_ip] = now
    return True


def _cache_key(payload: SuggestRequest, user_id: str) -> str:
    """Same pantry + settings on the same Japan date reuse one AI result.

    refresh_nonce is deliberately excluded: the old implementation included it,
    so every click on "もう一度提案" bypassed the cache and consumed quota.
    """
    serializable = {
        "user_id": user_id,
        "pantry": sorted(
            [item.model_dump(mode="json") for item in payload.pantry],
            key=lambda item: (item["name"], item["expiry_date"], item["quantity"], item["unit"]),
        ),
        "preferences": payload.preferences.model_dump(mode="json"),
        "japan_date": today_japan().isoformat(),
        "model": GEMINI_MODEL,
        "prompt_version": PROMPT_VERSION,
    }
    raw = json.dumps(serializable, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_persistent_recipe_cache(cache_key: str) -> dict[str, Any] | None:
    now = time.time()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT result_json, expires_at FROM recipe_suggestion_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        if float(row["expires_at"]) <= now:
            connection.execute("DELETE FROM recipe_suggestion_cache WHERE cache_key = ?", (cache_key,))
            return None
        try:
            result = json.loads(row["result_json"])
        except (TypeError, json.JSONDecodeError):
            connection.execute("DELETE FROM recipe_suggestion_cache WHERE cache_key = ?", (cache_key,))
            return None
    if not isinstance(result, dict):
        return None
    return {
        **result,
        "cached": True,
        "message": "同じ食材・予算・時間のAI提案をSQLiteキャッシュから再表示しています。Gemini APIへの新しいリクエストは送信していません。",
    }


def _write_persistent_recipe_cache(cache_key: str, result: dict[str, Any]) -> None:
    now = time.time()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO recipe_suggestion_cache (cache_key, result_json, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                result_json = excluded.result_json,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (cache_key, json.dumps(result, ensure_ascii=False), now, now + CACHE_SECONDS),
        )
        # Keep only the most recent 100 cache records.
        connection.execute(
            "DELETE FROM recipe_suggestion_cache WHERE cache_key NOT IN "
            "(SELECT cache_key FROM recipe_suggestion_cache ORDER BY created_at DESC LIMIT 100)"
        )


def _reserve_daily_gemini_request() -> tuple[bool, int]:
    """Persist an app-side daily safety cap; cache hits never reach this function."""
    today = today_japan().isoformat()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT request_count FROM gemini_daily_usage WHERE usage_date = ?", (today,)
        ).fetchone()
        used = int(row["request_count"]) if row else 0
        if used >= MAX_REQUESTS_PER_DAY:
            return False, used
        connection.execute(
            """
            INSERT INTO gemini_daily_usage (usage_date, request_count) VALUES (?, 1)
            ON CONFLICT(usage_date) DO UPDATE SET request_count = request_count + 1
            """,
            (today,),
        )
        return True, used + 1


@app.get("/api/pantry")
def get_pantry(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    with db_connection() as connection:
        _ensure_user_state(connection, user["id"])
        return _read_pantry_state(connection, user["id"])


@app.post("/api/auth/register", response_model=AuthSession)
def register(payload: AuthCredentials) -> dict[str, str]:
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="有効なメールアドレスを入力してください")
    with db_connection() as connection:
        if connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="このメールアドレスは既に登録されています")
        user_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, email, _password_hash(payload.password), datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()),
        )
        _ensure_user_state(connection, user_id)
        if connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"] == 1:
            connection.execute("UPDATE pantry_items SET user_id = ? WHERE user_id IS NULL", (user_id,))
            connection.execute("UPDATE app_state SET user_id = ? WHERE id = 1 AND user_id IS NULL", (user_id,))
    return _create_session(user_id, email)


@app.post("/api/auth/login", response_model=AuthSession)
def login(payload: AuthCredentials) -> dict[str, str]:
    email = payload.email.strip().lower()
    with db_connection() as connection:
        user = connection.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    if user is None or not _verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="メールアドレスまたはパスワードが違います")
    return _create_session(user["id"], user["email"])


def _create_session(user_id: str, email: str) -> dict[str, str]:
    token = secrets.token_urlsafe(32)
    with db_connection() as connection:
        connection.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_token_hash(token), user_id, time.time() + 60 * 60 * 24 * 30),
        )
    return {"token": token, "email": email}


@app.get("/api/auth/me", response_model=AuthSession)
def get_current_session(request: Request) -> dict[str, str]:
    user = _current_user(request)
    return {"token": "", "email": user["email"]}


@app.post("/api/auth/logout")
def logout(request: Request) -> dict[str, bool]:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        with db_connection() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_token_hash(authorization[7:].strip()),))
    return {"loggedOut": True}


@app.post("/api/pantry")
def create_pantry_item(payload: PantryItemWrite, request: Request) -> dict[str, Any]:
    user = _current_user(request)
    with db_connection() as connection:
        _ensure_user_state(connection, user["id"])
        return _insert_pantry_item(connection, payload, user["id"])


@app.put("/api/pantry/reset")
def reset_pantry(request: Request, payload: list[PantryItemWrite] = Body(max_length=200)) -> dict[str, Any]:
    user = _current_user(request)
    with db_connection() as connection:
        _ensure_user_state(connection, user["id"])
        connection.execute("DELETE FROM pantry_items WHERE user_id = ?", (user["id"],))
        connection.execute("UPDATE app_state SET consumed_count = 0, initialized = 1 WHERE user_id = ?", (user["id"],))
        for item in payload:
            _insert_pantry_item(connection, item, user["id"])
        return _read_pantry_state(connection, user["id"])


@app.put("/api/pantry/{item_id}")
def update_pantry_item(item_id: str, payload: PantryItemWrite, request: Request) -> dict[str, Any]:
    user = _current_user(request)
    with db_connection() as connection:
        result = connection.execute(
            """UPDATE pantry_items
               SET name = ?, quantity = ?, unit = ?, expiry_date = ?, category = ?, emoji = ?, note = ?
               WHERE id = ? AND user_id = ?""",
            (payload.name.strip(), payload.quantity, payload.unit, payload.expiryDate.isoformat(),
             payload.category, payload.emoji, payload.note, item_id, user["id"]),
        )
        if result.rowcount == 0:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="食材が見つかりません")
        connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user["id"],))
        row = connection.execute("SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"])).fetchone()
        return _db_item_to_api(row)


@app.delete("/api/pantry/{item_id}")
def delete_pantry_item(item_id: str, request: Request) -> dict[str, bool]:
    user = _current_user(request)
    with db_connection() as connection:
        result = connection.execute("DELETE FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"]))
        if result.rowcount == 0:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="食材が見つかりません")
        connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user["id"],))
    return {"deleted": True}


@app.post("/api/pantry/{item_id}/consume")
def consume_pantry_item(item_id: str, request: Request) -> dict[str, Any]:
    user = _current_user(request)
    with db_connection() as connection:
        row = connection.execute("SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"])).fetchone()
        if row is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="食材が見つかりません")
        if float(row["quantity"]) <= 1:
            connection.execute("DELETE FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"]))
            connection.execute("UPDATE app_state SET consumed_count = consumed_count + 1, initialized = 1 WHERE user_id = ?", (user["id"],))
            updated_item = None
        else:
            connection.execute(
                "UPDATE pantry_items SET quantity = quantity - 1 WHERE id = ? AND user_id = ?", (item_id, user["id"])
            )
            connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user["id"],))
            updated = connection.execute("SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"])).fetchone()
            updated_item = _db_item_to_api(updated)
        state = connection.execute("SELECT consumed_count FROM app_state WHERE user_id = ?", (user["id"],)).fetchone()
        return {"item": updated_item, "consumedCount": int(state["consumed_count"])}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "mottainai-kitchen-api",
        "version": APP_VERSION,
        "geminiConfigured": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL if GEMINI_API_KEY else None,
    }


@app.post("/api/recipes/suggest")
def suggest_recipes(payload: SuggestRequest, request: Request) -> dict[str, Any]:
    user = _current_user(request)
    key = _cache_key(payload, user["id"])

    # 1) Check SQLite cache first. This path does not call Gemini and does not
    # consume the provider quota or our own daily request allowance.
    cached = _read_persistent_recipe_cache(key)
    if cached is not None:
        return cached

    fallback = _format_fallback(payload.pantry, payload.preferences)
    if not GEMINI_API_KEY:
        return {
            "recipes": fallback,
            "source": "local",
            "cached": False,
            "message": "Gemini APIキーが未設定のため、アプリ内の節約レシピを表示しています。",
        }

    client_ip = request.client.host if request.client else "unknown"
    if not _check_request_limit(client_ip):
        return {
            "recipes": fallback,
            "source": "local",
            "cached": False,
            "message": "アプリ側の連続リクエスト防止制限に達しました。20秒以上待ってから再試行してください。サンプルレシピを表示しています。",
        }

    allowed, daily_used = _reserve_daily_gemini_request()
    if not allowed:
        return {
            "recipes": fallback,
            "source": "local",
            "cached": False,
            "message": f"アプリ側でGemini呼び出しを1日{MAX_REQUESTS_PER_DAY}回までに制限しています（本日{daily_used}回使用）。翌日以降に再試行してください。サンプルレシピを表示しています。",
        }

    try:
        raw = _gemini_generate(_build_prompt(payload))
        recipes = _format_gemini_recipes(raw, payload.pantry)
        # Enforce user's selected bounds even if the model ignores the prompt.
        recipes = [
            recipe for recipe in recipes
            if recipe["minutes"] <= payload.preferences.max_minutes
            and recipe["estimatedCostYen"] <= payload.preferences.budget_yen
        ]
        if not recipes:
            raise RuntimeError("選択した予算・調理時間に合うレシピを生成できませんでした。食材や予算を変更して再提案してください。")
        result = {
            "recipes": recipes,
            "source": "gemini",
            "cached": False,
            "message": f"{GEMINI_MODEL} が一人分・節約・時短の条件で提案しました。成功した提案はSQLiteに24時間保存し、同じ条件ではAPIを再利用しません。材料費は概算です。",
        }
        _write_persistent_recipe_cache(key, result)
        return result
    except RuntimeError as exc:
        return {
            "recipes": fallback,
            "source": "local",
            "cached": False,
            "message": f"{str(exc)} サンプルレシピを表示しています。",
        }
