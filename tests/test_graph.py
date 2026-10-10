"""グラフビュー（app/core/graph.py）の深さの読み取りと距離の計算の契約テスト

API を通した確認（公開ノートだけで探索する・上限で切る）は tests/test_api.py のローカルグラフのテストにある。
"""
import pytest

from app.core.graph import LinkGraph, distances_from, parse_depth


# ---------- parse_depth ----------

@pytest.mark.parametrize("value, expected", [
    ("1", 1), ("2", 2), (1, 1), (2, 2),
])
def test_深さは1と2を受け付ける(value, expected):
    assert parse_depth(value) == expected


@pytest.mark.parametrize("value", ["0", "3", "-1", "1.5", "abc", "", None, 99])
def test_深さが1と2以外なら1(value):
    assert parse_depth(value) == 1


# ---------- distances_from ----------

def _graph(links: list[tuple[str, str]], extra_nodes: tuple[str, ...] = ()) -> LinkGraph:
    names = {n for link in links for n in link} | set(extra_nodes)
    return LinkGraph(nodes={n: {"path": n} for n in sorted(names)}, links=links)


def test_1歩なら直接つながる点だけ():
    g = _graph([("中心", "A"), ("A", "B")])
    assert distances_from(g, "中心", 1) == {"中心": 0, "A": 1}


def test_2歩なら隣の隣まで():
    g = _graph([("中心", "A"), ("A", "B"), ("B", "C")])
    assert distances_from(g, "中心", 2) == {"中心": 0, "A": 1, "B": 2}


def test_リンクの向きは問わない():
    g = _graph([("A", "中心"), ("B", "A")])
    assert distances_from(g, "中心", 2) == {"中心": 0, "A": 1, "B": 2}


def test_近い道があればそちらの距離にする():
    g = _graph([("中心", "A"), ("A", "B"), ("中心", "B")])
    assert distances_from(g, "中心", 2) == {"中心": 0, "A": 1, "B": 1}


def test_輪になっていても止まる():
    g = _graph([("中心", "A"), ("A", "B"), ("B", "中心")])
    assert distances_from(g, "中心", 2) == {"中心": 0, "A": 1, "B": 1}


def test_つながりが無ければ中心だけ():
    g = _graph([("A", "B")], extra_nodes=("中心",))
    assert distances_from(g, "中心", 2) == {"中心": 0}


def test_自分へのリンクは距離を変えない():
    g = _graph([("中心", "中心"), ("中心", "A")])
    assert distances_from(g, "中心", 1) == {"中心": 0, "A": 1}
