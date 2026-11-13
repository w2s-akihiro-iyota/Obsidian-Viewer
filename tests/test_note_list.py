"""ノート一覧（app/core/note_list.py）の並び替え・公開状態の絞り込み・タグの集計の契約テスト

画面を通した確認（外部には公開ノートだけ・チップ・ページ送り）は tests/test_api.py の一覧のテストにある。
"""
from collections import Counter

import pytest

from app.core.note_list import (DEFAULT_SORT, DEFAULT_VISIBILITY, ListQuery, build_note_list, count_tags,
                                filter_visibility, sort_files)

FILES = [
    {"path": "b.md", "title": "beta", "mtime": 200, "char_count": 50, "published": True, "tags": ["仕事", "会議"]},
    {"path": "a.md", "title": "Alpha", "mtime": 300, "char_count": 10, "published": False, "tags": ["仕事"]},
    {"path": "c.md", "title": 2025, "mtime": 100, "published": True, "tags": None},
    {"path": "d.md", "title": "gamma", "mtime": 150, "char_count": 99, "published": None},
]


def _paths(files):
    return [f["path"] for f in files]


# ---------- sort_files ----------

def test_既定の並びは更新日の新しい順():
    assert DEFAULT_SORT == "updated"
    assert _paths(sort_files(FILES, "updated")) == ["a.md", "b.md", "d.md", "c.md"]


def test_更新日の古い順():
    assert _paths(sort_files(FILES, "updated_asc")) == ["c.md", "d.md", "b.md", "a.md"]


def test_タイトル順は大文字小文字を問わず数値のタイトルも文字として並べる():
    assert _paths(sort_files(FILES, "title")) == ["c.md", "a.md", "b.md", "d.md"]


def test_文字数の多い順で文字数が無ければ0とみなす():
    assert _paths(sort_files(FILES, "chars")) == ["d.md", "b.md", "a.md", "c.md"]


def test_並び替えは元の一覧を変えない():
    before = _paths(FILES)
    sort_files(FILES, "title")
    assert _paths(FILES) == before


def test_知らない並びはKeyError():
    # 不正な値は ListQuery.from_params で既定に倒してから渡す
    with pytest.raises(KeyError):
        sort_files(FILES, "unknown")


# ---------- filter_visibility ----------

def test_publicは公開ノートだけ():
    assert _paths(filter_visibility(FILES, "public")) == ["b.md", "c.md"]


def test_privateは公開でないノートだけでpublishedが無いものも含む():
    assert _paths(filter_visibility(FILES, "private")) == ["a.md", "d.md"]


@pytest.mark.parametrize("visibility", ["all", "unknown", ""])
def test_allと知らない値は全件の別の一覧を返す(visibility):
    result = filter_visibility(FILES, visibility)
    assert result == FILES
    assert result is not FILES


def test_既定の公開状態はall():
    assert DEFAULT_VISIBILITY == "all"


# ---------- count_tags ----------

def test_タグごとのノート数を数えタグが無いノートは飛ばす():
    assert count_tags(FILES) == Counter({"仕事": 2, "会議": 1})


def test_ノートが無ければ空():
    assert count_tags([]) == Counter()


# ---------- build_note_list の検索語（B-8） ----------

def _searched(q, include_private=True):
    return _paths(build_note_list(FILES, ListQuery(q=q), include_private=include_private, top_tag_count=10).files)


def test_検索語のtagはタグで絞り込み大文字小文字を問わない():
    assert _searched("tag:会議") == ["b.md"]
    assert _searched("TAG:仕事") == ["b.md", "a.md"]
    assert _searched("tag:#会議") == ["b.md"]


def test_検索語のpathはパスの一部で絞り込む():
    assert _searched("path:a") == ["a.md"]
    assert _searched('path:"c.md"') == ["c.md"]


def test_tagとpathと言葉を並べるとすべてに合うノートだけ():
    assert _searched("tag:仕事 alpha") == ["a.md"]
    assert _searched("tag:仕事 path:b") == ["b.md"]
    assert _searched("tag:会議 alpha") == []


def test_tagとpathが無ければ今までどおりタイトルかパスに含むノート():
    assert _searched("ALP") == ["a.md"]
    assert _searched("d.md") == ["d.md"]
    assert _searched("2025") == ["c.md"]


def test_外部の人には非公開ノートのタグで探しても出さない():
    assert _searched("tag:仕事", include_private=False) == ["b.md"]


# ---------- 外部の人の表示（F-17） ----------

def test_外部の人の表示のURLはas_publicを引き継ぐ():
    query = ListQuery.from_params(q="", tag="仕事", visibility="private", sort="title", page=2, include_private=False,
                                  public_view=True)
    assert query.visibility == DEFAULT_VISIBILITY   # 公開状態は効かない
    assert query.url() == "/?tag=%E4%BB%95%E4%BA%8B&sort=title&as=public"
    assert query.url(page=3) == "/?tag=%E4%BB%95%E4%BA%8B&sort=title&page=3&as=public"
    assert ListQuery(public_view=True).url() == "/?as=public"


def test_通常の表示のURLにはasを付けない():
    assert "as=" not in ListQuery(tag="仕事", sort="title").url()


def test_外部の人の表示のチップと条件を外すURLもas_publicを残す():
    query = ListQuery(q="メモ", tag="仕事", public_view=True)
    assert [f["url"] for f in query.active_filters()] == [
        "/?q=%E3%83%A1%E3%83%A2&as=public", "/?tag=%E4%BB%95%E4%BA%8B&as=public"]
    assert query.clear_url() == "/?as=public"
