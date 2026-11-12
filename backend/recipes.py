from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from datetime import date, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from config import (CACHE_SECONDS, GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_SECONDS, GEMINI_TOTAL_DEADLINE_SECONDS,
                    MAX_REQUESTS_PER_DAY, MAX_REQUESTS_PER_DAY_PER_USER, MAX_REQUESTS_PER_HOUR_PER_USER,
                    MIN_REQUEST_INTERVAL_SECONDS, PROMPT_VERSION)
from database import CurrentUser, _read_staples, db_connection
from ingredients import matches_name
from models import PantryInput, RecipePreferences, SuggestRequest

router = APIRouter(prefix="/api/recipes")

# Fallback recipes keep the core app usable when the API key is not configured,
# the free quota is temporarily exhausted, or the network is unavailable.
# "microwaveOnly": cookable without a stove (shown in the 電子レンジだけ mode).
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
    {
        "id": "spinach-egg",
        "name": "ほうれん草と卵のしょうゆ炒め",
        "description": "傷みやすい葉物を一気に使い切れる、フライパンひとつの副菜。",
        "minutes": 8,
        "difficulty": "かんたん",
        "emoji": "🥬",
        "ingredients": ["ほうれん草", "卵", "しょうゆ"],
        "ingredientDetails": ["ほうれん草 1/2袋", "卵 1個", "しょうゆ 小さじ1"],
        "steps": [
            "ほうれん草を洗い、4cm長さに切る。",
            "フライパンに油をひき、ほうれん草を茎から炒める。",
            "溶き卵を加え、卵にしっかり火が通るまで混ぜながら炒める。",
            "しょうゆを回し入れて全体になじませる。",
        ],
        "estimatedCostYen": 130,
    },
    {
        "id": "spinach-milk-pasta",
        "name": "ほうれん草のミルクスープパスタ",
        "description": "牛乳とコンソメで作る、生クリームなしのやさしいスープパスタ。",
        "minutes": 15,
        "difficulty": "かんたん",
        "emoji": "🍝",
        "ingredients": ["パスタ", "ほうれん草", "牛乳", "コンソメ"],
        "ingredientDetails": ["パスタ 80g", "ほうれん草 1/4袋", "牛乳 150ml", "コンソメ 小さじ1"],
        "steps": [
            "鍋に水200mlとコンソメを入れて沸かし、半分に折ったパスタを入れる。",
            "袋の表示時間どおりに混ぜながら煮る。",
            "ゆで上がり2分前に、4cmに切ったほうれん草を加える。",
            "牛乳を加えて弱火で温め、沸騰させないように仕上げる。",
        ],
        "estimatedCostYen": 200,
    },
    {
        "id": "teriyaki-chicken-don",
        "name": "鶏肉の照り焼き丼",
        "description": "甘辛だれでごはんが進む、ボリューム満点の一人丼。",
        "minutes": 15,
        "difficulty": "ふつう",
        "emoji": "🍗",
        "ingredients": ["ごはん", "鶏肉", "しょうゆ", "砂糖"],
        "ingredientDetails": ["ごはん 茶碗1杯", "鶏肉 120g", "しょうゆ 大さじ1", "砂糖 大さじ1/2"],
        "steps": [
            "鶏肉はひと口大に切る。",
            "フライパンで皮目から焼き、ふたをして弱めの中火で中まで火を通す。",
            "切り口が白くなったら、しょうゆと砂糖を加えて煮からめる。",
            "ごはんにのせ、たれをかける。",
        ],
        "estimatedCostYen": 260,
    },
    {
        "id": "moyashi-pork-steam",
        "name": "もやしと豚肉のレンジ蒸し",
        "description": "火を使わず電子レンジで完成。洗い物は耐熱皿だけ。",
        "minutes": 10,
        "difficulty": "かんたん",
        "emoji": "🥢",
        "ingredients": ["もやし", "豚肉", "ポン酢"],
        "ingredientDetails": ["もやし 1袋", "豚肉 80g", "ポン酢 大さじ1"],
        "steps": [
            "耐熱皿にもやしを広げ、豚肉を重ならないようにのせる。",
            "ふんわりラップをして、600Wで4〜5分加熱する。",
            "豚肉の赤い部分がなくなったか確認し、足りなければ30秒ずつ追加加熱する。",
            "ポン酢をかけていただく。",
        ],
        "estimatedCostYen": 200,
        "microwaveOnly": True,
    },
    {
        "id": "microwave-egg-don",
        "name": "レンジで作るふわふわ卵丼",
        "description": "コンロなしでOK。耐熱容器ひとつで作れる、朝にも夜にも使える丼。",
        "minutes": 6,
        "difficulty": "かんたん",
        "emoji": "🥚",
        "ingredients": ["ごはん", "卵", "めんつゆ"],
        "ingredientDetails": ["ごはん 茶碗1杯", "卵 1個", "めんつゆ 大さじ1"],
        "steps": [
            "耐熱容器に卵を溶き、めんつゆと水大さじ1を混ぜる。",
            "ふんわりラップをして600Wで1分加熱し、いったん取り出して混ぜる。",
            "さらに30秒〜1分、卵に火が通って固まるまで加熱する。",
            "温めたごはんにのせる。",
        ],
        "estimatedCostYen": 90,
        "microwaveOnly": True,
    },
    {
        "id": "microwave-cabbage-tuna",
        "name": "キャベツとツナのレンジ蒸し",
        "description": "キャベツを切ってのせてチンするだけ。余ったキャベツの消費に。",
        "minutes": 6,
        "difficulty": "かんたん",
        "emoji": "🥬",
        "ingredients": ["キャベツ", "ツナ缶", "ポン酢"],
        "ingredientDetails": ["キャベツ 2枚", "ツナ缶 1/2缶", "ポン酢 大さじ1"],
        "steps": [
            "キャベツをざく切りにして耐熱皿に広げる。",
            "油を軽く切ったツナをのせ、ふんわりラップをして600Wで3分加熱する。",
            "ポン酢をかけて全体を混ぜる。",
        ],
        "estimatedCostYen": 150,
        "microwaveOnly": True,
    },
    {
        "id": "carrot-kinpira",
        "name": "にんじんのきんぴら",
        "description": "にんじん1本を作り置きおかずに。お弁当にも使える。",
        "minutes": 10,
        "difficulty": "かんたん",
        "emoji": "🥕",
        "ingredients": ["にんじん", "しょうゆ", "砂糖", "ごま油"],
        "ingredientDetails": ["にんじん 1/2本", "しょうゆ 小さじ2", "砂糖 小さじ1", "ごま油 小さじ1"],
        "steps": [
            "にんじんを細切りにする。",
            "フライパンにごま油を熱し、にんじんがしんなりするまで炒める。",
            "しょうゆと砂糖を加え、汁気がなくなるまで炒める。",
        ],
        "estimatedCostYen": 60,
    },
    {
        "id": "tomato-egg-soup",
        "name": "トマトと卵のスープ",
        "description": "あと一品ほしいときに。トマトの酸味で食欲がない日にも。",
        "minutes": 8,
        "difficulty": "かんたん",
        "emoji": "🍅",
        "ingredients": ["トマト", "卵", "コンソメ"],
        "ingredientDetails": ["ミニトマト 5個", "卵 1個", "コンソメ 小さじ1"],
        "steps": [
            "ミニトマトを半分に切る。",
            "小鍋に水200mlとコンソメを入れて沸かし、トマトを入れて1分煮る。",
            "溶き卵を回し入れ、卵がふんわり固まるまでしっかり加熱する。",
        ],
        "estimatedCostYen": 120,
    },
    {
        "id": "natto-egg-udon",
        "name": "納豆たまごうどん",
        "description": "冷凍うどんで10分。たんぱく質もとれる忙しい日の味方。",
        "minutes": 10,
        "difficulty": "かんたん",
        "emoji": "🍜",
        "ingredients": ["うどん", "納豆", "卵", "めんつゆ"],
        "ingredientDetails": ["うどん 1玉", "納豆 1パック", "卵 1個", "めんつゆ 大さじ2"],
        "steps": [
            "うどんを袋の表示どおりに電子レンジで加熱する。",
            "フライパンで目玉焼きを作り、ふたをして黄身まで火を通す。",
            "うどんにめんつゆをかけ、納豆と卵をのせて混ぜる。",
        ],
        "estimatedCostYen": 170,
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


# Per-account Gemini call times (in memory; the daily counts live in SQLite).
_request_history: dict[str, list[float]] = {}
_last_request_at: dict[str, float] = {}
# FastAPI runs sync handlers in a thread pool: without a lock, two quick taps can both pass
# the interval check before either records its call, and both reach Gemini.
_rate_lock = threading.Lock()


def today_japan() -> date:
    return datetime.now(ZoneInfo("Asia/Tokyo")).date()


def matches_ingredient(required: str, pantry_item: PantryInput) -> bool:
    return matches_name(required, pantry_item.name)


def _is_available(ingredient: str, usable_pantry: list[PantryInput], staples: list[str]) -> bool:
    """In stock if a non-expired pantry item or a registered staple seasoning matches."""
    return (any(matches_ingredient(ingredient, item) for item in usable_pantry)
            or any(matches_name(ingredient, staple) for staple in staples))


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
        **({"storage": "冷凍保存中（使う前に解凍が必要。解凍の手間も調理時間に含める）"} if item.frozen else {}),
    }


def _build_prompt(request: SuggestRequest, pantry: list[PantryInput], staples: list[str]) -> str:
    today = today_japan()
    pantry_context = [_expiry_context(item, today) for item in pantry]
    usable = [row for row in pantry_context if row["days_until_expiry"] >= 0]
    expired = [row for row in pantry_context if row["days_until_expiry"] < 0]
    prefs = request.preferences
    equipment = ("- コンロ・フライパン・鍋は使わない。電子レンジ（と電気ケトル・炊飯器）だけで作れる手順にする。耐熱容器とラップで作れるものにする。"
                 if prefs.equipment == "microwave"
                 else "- フライパン、鍋、電子レンジ程度で作れる。一口コンロや狭いキッチンでも作りやすく、特殊な調理器具は使わない。")
    avoid = ""
    if request.exclude_recipe_names:
        avoid = f"""
【さっき提案した料理（今回は別の料理にする）】
{json.dumps(request.exclude_recipe_names, ensure_ascii=False)}
- 上の料理とは料理名も調理法も違うものにする（同じ料理の言い換えは不可）。
"""

    return f"""あなたは、日本の大学生の一人暮らしを助ける節約料理アドバイザーです。
今日の日付は {today.isoformat()} です。

【利用者像・必須条件】
- 大学生の一人暮らし。料理初心者でも作れる内容にする。
- 必ず1人分（servings=1）を想定する。
- 1食の食材費の目安は税込・概算で {prefs.budget_yen} 円以内を目指す。高価な食材は使わない。
- 調理時間は準備と加熱を含めて {prefs.max_minutes} 分以内を目指す。
{equipment}
- 洗い物が少なく、スーパーやコンビニで少量を買いやすい食材を優先する。
- 調味料を大量に買いそろえなくてよいレシピにする。
- ごはん、卵、豆腐、もやし、納豆、冷凍野菜、ツナ缶、パスタ、うどん等の安価な食材を活用する。

【登録されている食材】
{json.dumps(usable, ensure_ascii=False)}

【期限切れのため使ってはいけない食材】
{json.dumps(expired, ensure_ascii=False)}

【常備している調味料（買い足し不要・期限管理の対象外）】
{json.dumps(staples, ensure_ascii=False)}
{avoid}
【レシピ作成ルール】
1. 3つの異なるレシピを提案する。登録済み食材を優先し、期限が最も近いものを使えるレシピを上位候補にする。
2. 期限の優先順位は「今日まで > あと1日 > あと2日 > あと3日 > あと4〜7日 > 8日以上」。期限が今日〜3日以内の食材がある場合、可能な限りその食材を使う。
3. 期限切れの食材は絶対に材料に含めない。期限切れ食材を新しく買い足すような提案も避ける。
4. 買い足し材料はできるだけ少なくし、登録食材・常備調味料以外は原則2種類以内。調味料は常備調味料を優先する。
5. 食材名は照合しやすい短い名前（例「卵」「キャベツ」）にし、ingredientDetailsには1人分の分量（例「卵 1個」）を書く。
6. 手順は初心者向けに具体的な日本語で3〜6ステップにする。
7. 肉・魚・卵を使う場合は中心まで十分に加熱する手順にする。生食を前提にしない。
8. estimatedCostYenは1人分の材料費の概算整数。正確な販売価格ではないので現実的な目安にする。
9. 予算や時間を守れないレシピは作らない。3案は主食・丼・麺・おかず等でなるべく変化をつける。
10. 説明文や手順にMarkdown、コードブロック、JSON以外の前置きを含めない。

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
    started = time.monotonic()
    busy_message = "Gemini APIが一時的に混雑しています。自動で再試行しましたが接続できませんでした。しばらく待ってからもう一度提案してください。"
    for attempt in range(max_503_retries + 1):
        remaining = GEMINI_TOTAL_DEADLINE_SECONDS - (time.monotonic() - started)
        if remaining < 3:
            raise RuntimeError(busy_message)
        try:
            with urlopen(request, timeout=min(GEMINI_TIMEOUT_SECONDS, remaining)) as response:
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
                # Stop retrying if the wait would exceed the total deadline.
                if time.monotonic() - started + delay + 3 > GEMINI_TOTAL_DEADLINE_SECONDS:
                    raise RuntimeError(busy_message) from exc
                time.sleep(delay)
                continue
            if exc.code == 503:
                raise RuntimeError(busy_message) from exc
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
                    message = "Gemini APIの日次リクエスト上限に達しています。太平洋時間0時（日本時間16〜17時ごろ）のリセット後に再試行してください。"
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


def _format_gemini_recipes(raw: dict[str, Any], pantry: list[PantryInput], staples: list[str]) -> list[dict[str, Any]]:
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
            and not _is_available(ingredient, usable_pantry, staples)
            for ingredient in ingredients
        )
        if uses_expired_stock:
            continue
        matched = [ingredient for ingredient in ingredients if _is_available(ingredient, usable_pantry, staples)]
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


def _format_fallback(pantry: list[PantryInput], preferences: RecipePreferences, staples: list[str],
                     exclude_names: list[str] | None = None) -> list[dict[str, Any]]:
    today = today_japan()
    recipes: list[dict[str, Any]] = []
    for recipe in FALLBACK_RECIPES:
        if preferences.equipment == "microwave" and not recipe.get("microwaveOnly"):
            continue
        if recipe["minutes"] > preferences.max_minutes:
            continue
        if recipe["estimatedCostYen"] > preferences.budget_yen:
            continue
        usable_pantry = [item for item in pantry if item.expiry_date >= today]
        matched = [ingredient for ingredient in recipe["ingredients"] if _is_available(ingredient, usable_pantry, staples)]
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
    # On "別のレシピを提案", show recipes that were not on screen first.
    excluded = set(exclude_names or [])
    recipes.sort(key=lambda row: row["name"] in excluded)
    return recipes[:3]


def _user_rate_limit_message(user_id: str) -> str | None:
    """Short-term per-account limits (interval and hourly). Read-only: nothing is recorded here.
    Call with _rate_lock held, together with _record_user_request."""
    now = time.time()
    if now - _last_request_at.get(user_id, 0.0) < MIN_REQUEST_INTERVAL_SECONDS:
        return f"AI提案は{int(MIN_REQUEST_INTERVAL_SECONDS)}秒以上あけて使ってください。少し待ってから再試行してください。"
    recent = [stamp for stamp in _request_history.get(user_id, []) if now - stamp < 3600]
    _request_history[user_id] = recent
    if len(recent) >= MAX_REQUESTS_PER_HOUR_PER_USER:
        return f"AI提案は1時間に{MAX_REQUESTS_PER_HOUR_PER_USER}回までです。時間をおいて再試行してください。"
    return None


def _record_user_request(user_id: str) -> None:
    now = time.time()
    _last_request_at[user_id] = now
    _request_history.setdefault(user_id, []).append(now)


def _forget_user_request(user_id: str) -> None:
    """A failed call does not count toward the hourly limit (the interval still applies)."""
    with _rate_lock:
        history = _request_history.get(user_id)
        if history:
            history.pop()


def _cache_key(payload: SuggestRequest, pantry: list[PantryInput], user_id: str, staples: list[str]) -> str:
    """Same pantry + settings on the same Japan date reuse one AI result.

    refresh / exclude_recipe_names are deliberately excluded: a refresh overwrites this
    entry, so the next normal request shows the newest suggestions.
    """
    serializable = {
        "user_id": user_id,
        "pantry": sorted(
            [item.model_dump(mode="json") for item in pantry],
            key=lambda item: (item["name"], item["expiry_date"], item["quantity"], item["unit"]),
        ),
        "staples": sorted(staples),
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


def _write_persistent_recipe_cache(cache_key: str, user_id: str, result: dict[str, Any]) -> None:
    now = time.time()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO recipe_suggestion_cache (cache_key, user_id, result_json, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                result_json = excluded.result_json,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (cache_key, user_id, json.dumps(result, ensure_ascii=False), now, now + CACHE_SECONDS),
        )
        # Keep only the most recent 100 cache records.
        connection.execute(
            "DELETE FROM recipe_suggestion_cache WHERE cache_key NOT IN "
            "(SELECT cache_key FROM recipe_suggestion_cache ORDER BY created_at DESC LIMIT 100)"
        )


def _reserve_daily_gemini_request(user_id: str) -> str | None:
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


def _release_user_daily_request(user_id: str) -> None:
    """Give a failed call back to the account. The app-wide count is kept, because the
    provider may still have counted the attempt against the shared free quota."""
    with db_connection() as connection:
        connection.execute(
            "UPDATE gemini_user_daily_usage SET request_count = MAX(request_count - 1, 0) "
            "WHERE user_id = ? AND usage_date = ?",
            (user_id, today_japan().isoformat()),
        )


def _read_pantry_for_recipes(connection, user_id: str) -> list[PantryInput]:
    """The pantry as stored in SQLite: the single source of truth for suggestions, so a stale
    copy in a browser tab (or another device's edits) can never skew matching or the cache."""
    rows = connection.execute(
        "SELECT name, quantity, unit, expiry_date, category, frozen FROM pantry_items WHERE user_id = ? "
        "ORDER BY expiry_date ASC, created_at DESC LIMIT 200", (user_id,)
    ).fetchall()
    return [PantryInput(name=row["name"], quantity=row["quantity"], unit=row["unit"],
                        expiry_date=date.fromisoformat(row["expiry_date"]), category=row["category"],
                        frozen=bool(row["frozen"])) for row in rows]


@router.post("/suggest")
def suggest_recipes(payload: SuggestRequest, user: CurrentUser) -> dict[str, Any]:
    user_id = user["id"]
    with db_connection() as connection:
        staples = _read_staples(connection, user_id)
        pantry = _read_pantry_for_recipes(connection, user_id)
    key = _cache_key(payload, pantry, user_id, staples)

    # 1) Check SQLite cache first, unless the user explicitly asked for different recipes.
    # This path does not call Gemini and does not consume any quota or app-side allowance.
    if not payload.refresh:
        cached = _read_persistent_recipe_cache(key)
        if cached is not None:
            return cached

    fallback = _format_fallback(pantry, payload.preferences, staples, payload.exclude_recipe_names)

    def local(message: str) -> dict[str, Any]:
        return {"recipes": fallback, "source": "local", "cached": False, "message": message}

    if not GEMINI_API_KEY:
        return local("Gemini APIキーが未設定のため、アプリ内の節約レシピを表示しています。")

    with _rate_lock:
        limit_message = _user_rate_limit_message(user_id) or _reserve_daily_gemini_request(user_id)
        if not limit_message:
            _record_user_request(user_id)
    if limit_message:
        return local(f"{limit_message} アプリ内の節約レシピを表示しています。")

    try:
        raw = _gemini_generate(_build_prompt(payload, pantry, staples))
        recipes = _format_gemini_recipes(raw, pantry, staples)
        # Enforce user's selected bounds even if the model ignores the prompt.
        recipes = [
            recipe for recipe in recipes
            if recipe["minutes"] <= payload.preferences.max_minutes
            and recipe["estimatedCostYen"] <= payload.preferences.budget_yen
        ]
        if not recipes:
            raise RuntimeError("選択した予算・調理時間に合うレシピを生成できませんでした。食材や予算を変更して再提案してください。")
    except RuntimeError as exc:
        _release_user_daily_request(user_id)
        _forget_user_request(user_id)
        return local(f"{str(exc)} アプリ内の節約レシピを表示しています。")

    result = {
        "recipes": recipes,
        "source": "gemini",
        "cached": False,
        "message": f"{GEMINI_MODEL} が一人分・節約・時短の条件で提案しました。成功した提案はSQLiteに24時間保存し、同じ条件ではAPIを再利用しません。材料費は概算です。",
    }
    _write_persistent_recipe_cache(key, user_id, result)
    return result
