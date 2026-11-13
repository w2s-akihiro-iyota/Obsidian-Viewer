"""グラフビュー（app/core/graph.py）の深さの読み取りと距離の計算の契約テスト

API を通した確認（公開ノートだけで探索する・上限で切る）は tests/test_api.py のローカルグラフのテストにある。
"""
import pytest

from app import cache
from app.core.graph import LinkGraph, cached_link_graph, distances_from, parse_depth


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


def test_隣の点の表はリンクの向きを問わず初めて使うときに1回だけ作る():
    g = _graph([("a", "b"), ("c", "a")])
    assert g.neighbors == {"a": {"b", "c"}, "b": {"a"}, "c": {"a"}}
    assert g.neighbors is g.neighbors


# ---------- cached_link_graph（Q-15） ----------

def test_外部向けは公開ノートだけのグラフを使う(monkeypatch):
    admin, public = _graph([("a", "b")]), _graph([])
    monkeypatch.setattr(cache, "LINK_GRAPH", admin)
    monkeypatch.setattr(cache, "LINK_GRAPH_PUBLIC", public)
    assert cached_link_graph(False) is admin and cached_link_graph(True) is public


@pytest.mark.parametrize("published_only", [False, True])
def test_索引を作る前のグラフは空(monkeypatch, published_only):
    monkeypatch.setattr(cache, "LINK_GRAPH", None)
    monkeypatch.setattr(cache, "LINK_GRAPH_PUBLIC", None)
    graph = cached_link_graph(published_only)
    assert graph.nodes == {} and graph.links == []
