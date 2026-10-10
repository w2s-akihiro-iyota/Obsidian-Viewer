"""Dataview（app/core/dataview.py）のクエリの読み取り・条件の判定・HTML の組み立ての契約テスト

公開範囲での絞り込み（execute_query の published_only）は tests/test_api.py の公開チェックで確かめている。
ここでは入力と出力がはっきりした部分だけを確かめる。
"""
from datetime import datetime

import pytest

from app import cache
from app.core.dataview import (
    _evaluate_condition,
    _parse_condition,
    parse_query,
    render_list,
    render_table,
)


# ---------- parse_query ----------

def test_TABLEのフィールドとFROMとWHEREとSORTとLIMITを読む():
    q = parse_query('TABLE title, tags FROM "プロジェクト/" WHERE status = "done" AND rating >= 3 SORT updated ASC LIMIT 5')
    assert q.query_type == "TABLE"
    assert q.fields == ["title", "tags"]
    assert q.from_folder == "プロジェクト"
    assert q.from_tag == ""
    assert q.where_conditions == [("status", "=", "done"), ("rating", ">=", "3")]
    assert q.sort_field == "updated"
    assert q.sort_order == "ASC"
    assert q.limit == 5


def test_LISTはフィールドを持たずタグのFROMを読む():
    q = parse_query("LIST FROM #会議")
    assert q.query_type == "LIST"
    assert q.fields == []
    assert q.from_tag == "会議"
    assert q.from_folder == ""


def test_キーワードは大文字小文字を問わない():
    q = parse_query('table title from "a" where x = 1 sort title desc limit 2')
    assert (q.query_type, q.fields, q.from_folder) == ("TABLE", ["title"], "a")
    assert q.where_conditions == [("x", "=", "1")]
    assert (q.sort_field, q.sort_order, q.limit) == ("title", "DESC", 2)


def test_FROMが無くてもWHEREの前までをフィールドにする():
    q = parse_query("TABLE title, updated WHERE published = true")
    assert q.fields == ["title", "updated"]
    assert q.where_conditions == [("published", "=", "true")]


def test_SORTの向きを省くと新しい順で上限なし():
    q = parse_query("LIST SORT mtime")
    assert (q.sort_field, q.sort_order, q.limit) == ("mtime", "DESC", 0)


def test_読めない形のFROMは飛ばして次の句を読む():
    q = parse_query("LIST FROM [[ノート]] LIMIT 3")
    assert (q.from_folder, q.from_tag, q.limit) == ("", "", 3)


@pytest.mark.parametrize("text", ["TASK FROM #a", "CALENDAR file.mtime", ""])
def test_TABLEとLIST以外はエラーにする(text):
    with pytest.raises(ValueError):
        parse_query(text)


# ---------- _parse_condition ----------

@pytest.mark.parametrize("text, expected", [
    ('tags contains "会議"', ("tags", "contains", "会議")),
    ("tags CONTAINS 会議", ("tags", "contains", "会議")),
    ('status != "done"', ("status", "!=", "done")),
    ("rating>=3", ("rating", ">=", "3")),
    ("rating <= 3", ("rating", "<=", "3")),
    ("rating > 3", ("rating", ">", "3")),
    ("rating < 3", ("rating", "<", "3")),
    ("published = true", ("published", "=", "true")),
    ('file.name = "メモ"', ("file.name", "=", "メモ")),
])
def test_条件をフィールドと演算子と値に分ける(text, expected):
    assert _parse_condition(text) == expected


@pytest.mark.parametrize("text", ["", "status", "status is done"])
def test_読めない条件はNone(text):
    assert _parse_condition(text) is None


# ---------- _evaluate_condition ----------

NOTE = {
    "title": "定例会議",
    "path": "仕事/会議/定例.md",
    "name": "定例.md",
    "tags": ["会議", "仕事"],
    "char_count": 1200,
    "published": True,
    "updated": "2025-04-01 10:00",
    "mtime": datetime(2025, 4, 1, 10, 0),
    "frontmatter": {"status": "done", "rating": 4, "draft": "false"},
}


@pytest.mark.parametrize("field, op, value, expected", [
    # contains: リストは要素の完全一致（大文字小文字も区別）、文字列は大文字小文字を問わない部分一致
    ("tags", "contains", "会議", True),
    ("tags", "contains", "会", False),
    ("title", "contains", "会議", True),
    ("path", "contains", "仕事/会議", True),
    # 真偽値: true / false は文字列の "true" / "false" とも比べる
    ("published", "=", "true", True),
    ("published", "!=", "true", False),
    ("draft", "=", "false", True),
    # 数値: 両方が数値として読めれば数値で比べる
    ("char_count", ">", "999", True),
    ("char_count", "<=", "1200", True),
    ("rating", "=", "4.0", True),
    ("rating", "<", "4", False),
    # 文字列: それ以外は文字列で比べる（日付も文字列の大小）
    ("status", "=", "done", True),
    ("status", "!=", "done", False),
    ("updated", ">=", "2025-04-01", True),
    ("updated", "<", "2025-03-31", False),
    # file.* は Dataview と同じ意味で引く
    ("file.name", "=", "定例", True),
    ("file.folder", "=", "仕事/会議", True),
    ("file.path", "contains", "定例.md", True),
    ("file.size", ">", "1000", True),
])
def test_条件の判定(field, op, value, expected):
    assert _evaluate_condition(NOTE, field, op, value) is expected


def test_値の無いフィールドはノットイコールだけ満たす():
    assert _evaluate_condition(NOTE, "missing", "!=", "x") is True
    assert _evaluate_condition(NOTE, "missing", "=", "x") is False
    assert _evaluate_condition(NOTE, "missing", "contains", "x") is False
    assert _evaluate_condition(NOTE, "file.unknown", "!=", "x") is True


def test_フォルダ直下のノートのfile_folderは空文字():
    assert _evaluate_condition({"path": "直下.md"}, "file.folder", "=", "") is True


def test_読めない演算子は満たさない():
    assert _evaluate_condition(NOTE, "status", "~", "done") is False


# ---------- render_table / render_list ----------

RESULTS = [
    {"title": "<b>危険</b>", "path": "a/危険.md", "tags": ["x&y"], "updated": "2025-04-01 10:00", "published": True,
     "frontmatter": {}},
    {"title": "普通", "path": "b.md", "tags": [], "updated": None, "published": False, "frontmatter": {}},
]


@pytest.fixture
def slugs(monkeypatch):
    monkeypatch.setattr(cache, "PATH_TO_SLUG", {"a/危険.md": "a/kiken"})


def test_TABLEは見出しと行とリンクと件数を出しエスケープする(slugs):
    html = render_table(parse_query("TABLE tags, published, missing"), RESULTS)
    assert "<th>File</th><th>tags</th><th>published</th><th>missing</th>" in html
    assert '<a href="/view/a/kiken" class="dataview-link">&lt;b&gt;危険&lt;/b&gt;</a>' in html
    assert '<span class="dataview-tag">x&amp;y</span>' in html
    assert '<span class="dataview-badge-true">true</span>' in html
    assert '<span class="dataview-badge-false">false</span>' in html
    assert '<span class="dataview-null">-</span>' in html
    assert "<b>危険</b>" not in html
    assert "2件の結果" in html


def test_スラッグが無ければパスでリンクする(slugs):
    html = render_table(parse_query("TABLE title"), RESULTS)
    assert 'href="/view/b.md"' in html


def test_TABLEのフィールドを省くとタイトルとタグと更新日(slugs):
    html = render_table(parse_query("TABLE"), [])
    assert "<th>File</th><th>title</th><th>tags</th><th>updated</th>" in html
    assert "0件の結果" in html


def test_日時のフィールドは分までで出す(slugs):
    html = render_table(parse_query("TABLE mtime"), [{"title": "t", "path": "t.md", "mtime": datetime(2025, 4, 1, 9, 5, 30)}])
    assert "<td>2025-04-01 09:05</td>" in html


def test_LISTはアイコン付きのリンクの箇条書きでエスケープする(slugs):
    html = render_list(parse_query("LIST"), RESULTS)
    assert html.count("<li>") == 2
    assert 'href="/view/a/kiken" class="dataview-list-link"' in html
    assert 'class="dataview-note-icon"' in html
    assert '<span class="dataview-list-title">&lt;b&gt;危険&lt;/b&gt;</span>' in html
    assert "2件の結果" in html
