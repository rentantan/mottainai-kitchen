"""Gemini API: the recipe prompt, the response schema and the HTTP call (with 503 retries)."""
from __future__ import annotations

import json
import random
import time
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from clock import today_japan
from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_SECONDS, GEMINI_TOTAL_DEADLINE_SECONDS
from models import PantryInput, SuggestRequest

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
                    "ingredientDetails": {"type": "array", "items": {"type": "string"},
                                          "description": "ingredientsと同じ数・同じ順番の1人分の分量（例「卵 1個」）"},
                    "steps": {"type": "array", "items": {"type": "string"},
                              "description": "初心者向けの手順4〜8個。火加減・時間・切り方の大きさ・調味料の量・次へ進む見た目の目安を含める"},
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


def build_prompt(request: SuggestRequest, pantry: list[PantryInput], staples: list[str]) -> str:
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
5. 食材名は照合しやすい短い名前（例「卵」「キャベツ」）にし、ingredientDetailsには1人分の分量（例「卵 1個」）を書く。ingredientDetailsはingredientsと同じ数・同じ順番にする。
   - 手順で使う油・調味料はすべてingredientsとingredientDetailsにも入れる（水だけは入れなくてよい）。逆に、手順で使わない材料は入れない。
6. 手順は、包丁やフライパンをほとんど使ったことがない人が手順だけを見て迷わず作れるように、4〜8ステップで具体的に書く。各ステップは1〜2文。
   - 火加減（弱火・中火・強火）と、加熱や炒める時間の目安（例「中火で2〜3分」）を必ず書く。電子レンジは「600Wで◯分」と書く。
   - 次へ進む目安を見た目で書く（例「卵のふちが固まってきたら」「キャベツが少し透き通ってきたら」「切った中が白くなっていれば火が通っている」）。
   - 切り方は大きさも書く（例「4〜5cm角」「1cm幅」「4cm長さ」）。
   - 調味料・油・水は、入れる手順の中で量も書く（例「しょうゆ小さじ1を加える」）。「適量」「少々」だけで終わらせない（塩は「ひとつまみ」など具体的に）。
   - 卵を溶く、野菜を洗う、ヘタや根元を取る、たれを先に混ぜておく、といった下ごしらえも省略せず手順に含める。
   - 「鍋肌」「味を調える」「ひと煮立ち」「ざく切り」などの料理用語は使わないか、使う場合は同じ文で言い換える。
   - うまくいかないときの対処を1つ入れる（例「赤い部分があればさらに1分焼く」「固ければ30秒ずつ追加で加熱する」）。
   - 冷凍保存中の食材を使う場合は、解凍のしかた（例「600Wで1分30秒温める」「凍ったまま入れてよい」）も手順に書く。
   - minutesは、手順に書いた下ごしらえ・加熱・待ち時間の合計と合う値にする。
7. 肉・魚・卵を使う場合は中心まで十分に加熱する手順にする。生食を前提にしない。生の肉・魚を切った包丁とまな板は、続けて野菜などに使う前に洗うよう手順に書く。
8. estimatedCostYenは1人分の材料費の概算整数。正確な販売価格ではないので現実的な目安にする。
9. 予算や時間を守れないレシピは作らない。3案は主食・丼・麺・おかず等でなるべく変化をつける。
10. 説明文や手順にMarkdown、コードブロック、JSON以外の前置きを含めない。

JSONスキーマに従って、recipes配列だけを返してください。"""


def generate(prompt: str) -> dict[str, Any]:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY が設定されていません")

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.65,
            "maxOutputTokens": 6000,
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
