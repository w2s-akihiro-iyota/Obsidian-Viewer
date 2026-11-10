"""プロパティの表示用モデル（app/core/properties.py）の契約テスト

F-12: frontmatter の項目を、書いてある順に・空を除いて・リンクを本文と同じ決め方で並べる
"""
from datetime import date, datetime

import pytest

from app import cache
from app.core.note_resolver import NoteResolver
from app.core.properties import (HIDDEN_KEYS, ChipsProperty, NestedProperty, PropertyLink, PropertyText,
                                 TextProperty, build_properties)

NOTES = ["wiki/概念.md", "wiki/別名.md", "メモ.md"]


@pytest.fixture
def vault(monkeypatch):
    monkeypatch.setattr(cache, "NOTE_RESOLVER", NoteResolver([(r, None) for r in NOTES]))
    monkeypatch.setattr(cache, "PATH_TO_SLUG", {r: r[:-3] for r in NOTES})
    monkeypatch.setattr(cache, "MEDIA_INDEX", None)


def build(frontmatter, source="メモ.md"):
    return build_properties(frontmatter, source)


def by_key(props):
    return {p.key: p for p in props}


def test_書いてある順に並べtitleとtagsとpublishは出さない(vault):
    props = build({"type": "lesson", "title": "題", "tags": ["a"], "publish": True, "genre": "dev"})
    assert [p.key for p in props] == ["type", "genre"]
    assert HIDDEN_KEYS == {"title", "tags", "publish"}


def test_空の値の項目は出さない(vault):
    props = build({"a": None, "b": "", "c": "  ", "d": [], "e": {}, "f": [None, "", " "], "g": {"x": None}, "h": "ok"})
    assert [p.key for p in props] == ["h"]


def test_0とfalseは空ではない(vault):
    props = by_key(build({"n": 0, "b": False}))
    assert props["n"].parts == (PropertyText("0"),)
    assert props["b"].parts == (PropertyText("いいえ"),)


def test_値の型ごとの見せ方(vault):
    props = by_key(build({
        "d": date(2026, 10, 16), "dt": datetime(2026, 11, 10, 18, 41, 5), "yes": True, "n": 3, "f": 1.5, "s": "文字",
    }))
    assert props["d"].parts == (PropertyText("2026-10-16"),)
    assert props["dt"].parts == (PropertyText("2026-11-10 18:41"),)
    assert props["yes"].parts == (PropertyText("はい"),)
    assert props["n"].parts == (PropertyText("3"),)
    assert props["f"].parts == (PropertyText("1.5"),)
    assert isinstance(props["s"], TextProperty)


def test_HTMLは組み立てずそのまま持つ(vault):
    props = build({"s": "<b>x</b> & [[<i>]]"})
    assert props[0].parts[0] == PropertyText("<b>x</b> & ")
    assert props[0].parts[1] == PropertyLink("<i>", None)   # エスケープはテンプレート側


def test_文字列の中のリンクはリンクとリンク切れと見出しに分かれる(vault):
    p = build({"s": "前 [[概念]] 中 [[ない]] [[概念|別の名前]] [[概念#節 1]] [[#内]] 後"})[0]
    assert p.parts == (
        PropertyText("前 "), PropertyLink("概念", "/view/wiki/概念"),
        PropertyText(" 中 "), PropertyLink("ない", None),
        PropertyText(" "), PropertyLink("別の名前", "/view/wiki/概念"),
        PropertyText(" "), PropertyLink("概念 > 節 1", "/view/wiki/概念#節-1"),
        PropertyText(" "), PropertyLink("内", "#内"),
        PropertyText(" 後"),
    )


def test_リストは札になりリンクの要素もリンクになる(vault):
    p = build({"related": ["[[概念]]", "[[ない]]", "文字", None, "", 5]})[0]
    assert isinstance(p, ChipsProperty)
    assert p.chips == (
        (PropertyLink("概念", "/view/wiki/概念"),), (PropertyLink("ない", None),),
        (PropertyText("文字"),), (PropertyText("5"),),
    )


def test_辞書は1段だけキーと値で出しさらに深いものは文字列にする(vault):
    p = build({"captured_from": {"cwd": "C:/x", "repo": None, "deep": {"a": 1, "b": [1, 2]}, "dt": date(2026, 1, 2),
                                  "link": "[[概念]]"}})[0]
    assert isinstance(p, NestedProperty)
    assert p.nested == (
        ("cwd", (PropertyText("C:/x"),)),
        ("deep", (PropertyText("a: 1, b: 1, 2"),)),
        ("dt", (PropertyText("2026-01-02"),)),
        ("link", (PropertyLink("概念", "/view/wiki/概念"),)),
    )


def test_リンク先は同じフォルダのノートを優先する(monkeypatch):
    notes = ["a/同名.md", "b/同名.md", "b/元.md"]
    monkeypatch.setattr(cache, "NOTE_RESOLVER", NoteResolver([(r, None) for r in notes]))
    monkeypatch.setattr(cache, "PATH_TO_SLUG", {r: r[:-3] for r in notes})
    monkeypatch.setattr(cache, "MEDIA_INDEX", None)
    assert build({"r": "[[同名]]"}, source="b/元.md")[0].parts == (PropertyLink("同名", "/view/b/同名"),)
    assert build({"r": "[[同名]]"}, source="a/x.md")[0].parts == (PropertyLink("同名", "/view/a/同名"),)


def test_frontmatterが辞書でなければ空(vault):
    assert build(None) == () and build("x") == () and build([1]) == ()


def test_モデルは読み取り専用(vault):
    p = build({"a": "x"})[0]
    with pytest.raises(Exception):
        p.key = "b"


def test_YAMLのアンカーで循環する値でも落ちず循環の箇所は省略する(vault):
    import yaml
    fm = yaml.safe_load(chr(10).join(["a: &x [1, *x]", "b: &y {k: v, self: *y}", "c: [[q, 1]]"]))
    props = by_key(build(fm))
    assert props["a"].chips == ((PropertyText("1"),), (PropertyText("…"),))
    assert props["b"].nested == (("k", (PropertyText("v"),)), ("self", (PropertyText("…"),)))


def test_アンカーで膨らむ値でも一定時間で終わる(vault):
    import time
    import yaml
    from app.services import wikilinks
    lines = ["l0: &l0 ['[[a]]', '[[b]]', '[[c]]', '[[d]]', '[[e]]', '[[f]]']"]
    for i in range(1, 12):
        lines.append(f"l{i}: &l{i} [*l{i - 1}, *l{i - 1}, *l{i - 1}, *l{i - 1}, *l{i - 1}, *l{i - 1}]")
    fm = yaml.safe_load(chr(10).join(lines))
    start = time.perf_counter()
    links = list(wikilinks.iter_frontmatter_wikilinks(fm))
    build(fm)
    assert time.perf_counter() - start < 0.5
    assert len(links) == 6
