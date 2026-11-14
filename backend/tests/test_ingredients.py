import re
from pathlib import Path

import pytest

from ingredients import ALIAS_GROUPS, matches_name


@pytest.mark.parametrize("required, name", [
    ("鶏肉", "鶏もも肉"),
    ("鶏肉", "鶏むね肉"),
    ("ねぎ", "ネギ"),
    ("しょうゆ", "醤油"),
    ("ごはん", "ご飯"),
    ("卵", "たまご"),
    ("トマト", "ミニトマト"),
    ("うどん", "冷凍うどん"),
    ("ツナ缶", "シーチキン"),
    ("パスタ", "ｽﾊﾟｹﾞｯﾃｨ"),  # half-width katakana
    ("豆腐", "絹 豆腐"),
    ("鶏肉", "国産鶏もも肉"),
    ("ねぎ", "九条ねぎ"),
    ("しょうゆ", "減塩醤油"),
    ("ひき肉", "豚ひき肉"),
    ("こしょう", "黒こしょう"),
    ("油", "サラダ油"),
    ("卵", "卵(Mサイズ)"),
    ("キャベツ", "キャベツ1/2"),
    ("豆腐", "豆腐半分"),
])
def test_matches_spelling_variants(required, name):
    assert matches_name(required, name)
    assert matches_name(name, required)


@pytest.mark.parametrize("required, name", [
    ("鶏肉", "豚肉"),
    ("玉ねぎ", "にんじん"),
    ("卵", "牛乳"),
    ("", "卵"),
    # A shorter name that merely appears inside another food's name.
    ("ねぎ", "玉ねぎ"),
    ("長ねぎ", "玉ねぎ"),
    ("ねぎ", "新玉ねぎ"),
    ("油", "醤油"),
    ("油", "ごま油"),
    ("酢", "ポン酢"),
    ("米", "米酢"),
    ("塩", "塩こしょう"),
    ("卵", "卵豆腐"),
    ("牛乳", "豆乳"),
    ("豆腐", "豆腐ハンバーグ"),
])
def test_does_not_match_different_foods(required, name):
    assert not matches_name(required, name)
    assert not matches_name(name, required)


def test_frontend_alias_groups_match_backend():
    """frontend/src/lib/ingredients.ts must use the same alias groups as backend/ingredients.py."""
    ingredients_ts = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "ingredients.ts").read_text(encoding="utf-8")
    block = ingredients_ts.split("INGREDIENT_ALIAS_GROUPS: string[][] = [", 1)[1].split("\n]", 1)[0]
    frontend = [re.findall(r"'([^']+)'", line) for line in block.splitlines() if line.strip().startswith("[")]
    assert frontend == ALIAS_GROUPS
