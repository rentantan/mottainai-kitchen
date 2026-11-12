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
    # Single-character seasonings get their own groups so that the longest-suffix rule
    # below tells them apart from longer names that merely end with them (醤油 ≠ 油, ポン酢 ≠ 酢).
    ["サラダ油", "油", "植物油", "キャノーラ油", "サラダオイル"],
    ["ごま油"],
    ["ラー油"],
    ["オリーブオイル", "オリーブ油"],
    ["酢", "米酢", "穀物酢"],
    ["塩", "食塩", "あら塩"],
    ["酒", "料理酒", "日本酒"],
    ["みりん", "本みりん"],
]


def _fold_kana(value: str) -> str:
    """Katakana → hiragana so ネギ / ねぎ compare equal."""
    return "".join(chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in value)


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value)
    return _fold_kana(re.sub(r"\s", "", folded)).lower()


# Bracketed notes ("卵(Mサイズ)"), amounts ("キャベツ1/2") and leftover words ("豆腐半分")
# are not part of the food name.
_BRACKETS = re.compile(r"\(.*?\)|\[.*?\]|【.*?】|「.*?」")
_TRAILING_AMOUNT = re.compile(r"(?<=.)\d.*$")
_TRAILING_WORDS = re.compile(r"(半分|半玉|半丁|半袋|少々|適量|適宜|残り)$")


def _core(value: str) -> str:
    core = _BRACKETS.sub("", normalize(value))
    core = _TRAILING_AMOUNT.sub("", core)
    return _TRAILING_WORDS.sub("", core) or normalize(value)


_CANONICAL: dict[str, str] = {
    normalize(alias): normalize(group[0]) for group in ALIAS_GROUPS for alias in group
}
# Longest first, so "玉ねぎ" wins over "ねぎ" and "醤油" over "油".
_ALIASES_BY_LENGTH = sorted(_CANONICAL, key=len, reverse=True)


def canonical(value: str) -> str:
    normalized = normalize(value)
    return _CANONICAL.get(normalized, normalized)


def head_food(value: str) -> str | None:
    """Canonical food a name refers to, found from its longest known ending.

    Japanese food names put modifiers first, so the known name at the end decides the food:
    "国産鶏もも肉" → 鶏肉, "新玉ねぎ" → 玉ねぎ, "九条ねぎ" → ねぎ, "卵豆腐" → 豆腐.
    Returns None for names that end with no known food (e.g. "ミニトマト").
    """
    core = _core(value)
    for alias in _ALIASES_BY_LENGTH:
        if core.endswith(alias):
            return _CANONICAL[alias]
    return None


def matches_name(required: str, name: str) -> bool:
    """True when two ingredient names refer to the same food.

    - Names whose ending is a known food match only when that food is the same
      (長ねぎ ≠ 玉ねぎ, 卵 ≠ 卵豆腐, 油 ≠ 醤油).
    - Otherwise the shorter name (2+ characters) must be the ending of the longer one
      (トマト ≒ ミニトマト, うどん ≒ 冷凍うどん), so a single character never matches
      something else by accident (米 ≠ 米酢, 酢 ≠ ポン酢).
    """
    a, b = _core(required), _core(name)
    if not a or not b:
        return False
    if a == b:
        return True
    head_a, head_b = head_food(a), head_food(b)
    if head_a is not None or head_b is not None:
        return head_a == head_b
    shorter, longer = sorted((a, b), key=len)
    return len(shorter) >= 2 and longer.endswith(shorter)
