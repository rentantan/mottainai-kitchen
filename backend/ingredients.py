"""Ingredient-name matching shared by Gemini and fallback recipes.

Keep ALIAS_GROUPS and the normalisation rules in sync with
frontend/src/utils.ts (INGREDIENT_ALIAS_GROUPS / normalize).
"""
from __future__ import annotations

import re
import unicodedata

# Each group lists spellings of the same ingredient; the first entry is the canonical name.
# Katakana/hiragana and full/half-width differences are folded by normalize(), so only
# genuinely different spellings (kanji, other words) need to be listed here.
ALIAS_GROUPS: list[list[str]] = [
    ["ごはん", "ご飯", "白米", "米", "ライス", "白ごはん"],
    ["卵", "たまご", "玉子", "鶏卵"],
    ["鶏肉", "鶏もも肉", "鶏むね肉", "鶏胸肉", "鶏もも", "鶏むね", "とり肉", "ささみ", "鶏ささみ"],
    ["豚肉", "豚こま", "豚こま肉", "豚こま切れ肉", "豚バラ", "豚バラ肉", "豚ロース"],
    ["ひき肉", "挽き肉", "挽肉", "合いびき肉", "合挽き肉"],
    ["ねぎ", "長ねぎ", "青ねぎ", "万能ねぎ", "小ねぎ", "葱", "長葱"],
    ["玉ねぎ", "たまねぎ", "玉葱"],
    ["にんじん", "人参"],
    ["じゃがいも", "じゃが芋", "馬鈴薯"],
    ["ほうれん草", "ほうれんそう"],
    ["しょうゆ", "醤油", "しょう油"],
    ["塩こしょう", "塩胡椒"],
    ["こしょう", "胡椒"],
    ["砂糖", "さとう"],
    ["味噌", "みそ"],
    ["豆腐", "とうふ", "絹豆腐", "木綿豆腐"],
    ["ツナ缶", "ツナ", "シーチキン"],
    ["パスタ", "スパゲッティ", "スパゲティ"],
    ["牛乳", "ミルク"],
    ["しめじ", "ぶなしめじ"],
    ["コンソメ", "顆粒コンソメ", "固形コンソメ"],
    ["めんつゆ", "麺つゆ"],
    ["ポン酢", "ぽんず"],
]


def _fold_kana(value: str) -> str:
    """Katakana → hiragana so ネギ / ねぎ compare equal."""
    return "".join(chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in value)


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value)
    return _fold_kana(re.sub(r"\s", "", folded)).lower()


_CANONICAL: dict[str, str] = {
    normalize(alias): normalize(group[0]) for group in ALIAS_GROUPS for alias in group
}


def canonical(value: str) -> str:
    normalized = normalize(value)
    return _CANONICAL.get(normalized, normalized)


def matches_name(required: str, name: str) -> bool:
    """True when two ingredient names refer to the same food (substring or alias match)."""
    a, b = normalize(required), normalize(name)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    ca, cb = canonical(required), canonical(name)
    return ca in cb or cb in ca
