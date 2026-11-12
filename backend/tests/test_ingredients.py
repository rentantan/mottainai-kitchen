import pytest

from ingredients import matches_name


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
])
def test_matches_spelling_variants(required, name):
    assert matches_name(required, name)
    assert matches_name(name, required)


@pytest.mark.parametrize("required, name", [
    ("鶏肉", "豚肉"),
    ("玉ねぎ", "にんじん"),
    ("卵", "牛乳"),
    ("", "卵"),
])
def test_does_not_match_different_foods(required, name):
    assert not matches_name(required, name)
