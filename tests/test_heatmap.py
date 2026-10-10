"""ダッシュボードのヒートマップの濃さ（app/core/heatmap.py の heatmap_level）の契約テスト

マスの並びと月のラベルは tests/test_api.py（test_ヒートマップは53列で…）で確かめている。
濃さの段数はテンプレートの凡例と CSS の .level-N に合わせているので、段の境目を守る。
"""
import pytest

from app.config import HEATMAP_LEVEL_LIMITS
from app.core.heatmap import HEATMAP_LEVEL_COUNT, heatmap_level


def test_段数は0文字の段と区切りで分けた段():
    assert HEATMAP_LEVEL_LIMITS == (1000, 5000)
    assert HEATMAP_LEVEL_COUNT == 4


@pytest.mark.parametrize("chars, level", [
    (0, 0),
    (1, 1),
    (1000, 1),
    (1001, 2),
    (5000, 2),
    (5001, 3),
    (10 ** 7, 3),
])
def test_文字数から濃さを決め区切りちょうどは下の段(chars, level):
    assert heatmap_level(chars) == level


def test_濃さは段数を超えない():
    assert max(heatmap_level(n) for n in range(0, 20000, 250)) == HEATMAP_LEVEL_COUNT - 1
