"""タグを決める処理（app/core/tags.py）の契約テスト

本文の #タグ は、描画でタグの札（a.inline-tag）になるものだけを拾う。拾う・拾わないの境目と、描画との一致をここで固定する。
"""
import re

import pytest

from app.core.tag_syntax import tag_href
from app.core.tags import body_tags, frontmatter_tags, note_tags
from app.services.content import render_markdown


# ---------- body_tags: 拾う ----------

@pytest.mark.parametrize("body, expected", [
    ("#議事録", ["議事録"]),
    ("メモ #a/b です", ["a/b"]),
    ("チケット #PRODUCT_BASE-1095 を見る", ["PRODUCT_BASE-1095"]),
    ("1行目\n#行頭のタグ\n3行目", ["行頭のタグ"]),
    ("今週は #製品テスト の予定", ["製品テスト"]),
    ("これは #タグ。次の文", ["タグ"]),
    ("カッコ（ #タグ）", ["タグ"]),
    ("#a #b", ["a", "b"]),
    ("#階層/タグ/ の後ろの/は外す", ["階層/タグ"]),
    ("- #リストの中", ["リストの中"]),
    ("#2024年度", ["2024年度"]),
    ("> #引用", ["引用"]),
    (">#引用", ["引用"]),
    ("|a|b|\n|-|-|\n|#表|c|", ["表"]),
    ("#a #b #a", ["a", "b"]),
])
def test_本文のタグを拾う(body, expected):
    assert body_tags(body) == expected


# ---------- body_tags: 拾わない ----------

@pytest.mark.parametrize("body", [
    "PR #18）を直した",
    "#2024",
    "C# の話",
    "【#1】の件",
    "# 見出し",
    "## 見出し",
    "```\n#コードの中\n```",
    "`#インラインコード`",
    "[[ノート#見出し]]",
    "[[ノート #見出し]]",
    "https://x.com/#a",
    "[x](#a)",
    "[x]( #a)",
    "[解説 #C# - Qiita](https://example.com/p)",
    "![画像 #x](a.png)",
    "&#123;",
    '<span style="color:#fff">x</span>',
    "<a href=\"x\">a</a>#b",
    "文字#a",
    "**#強調の中**",
    "#/",
    "    #include <x>",
    "<!-- #a -->",
    "<div>\n#a\n</div>",
    "$a #b$",
    "`code`#tag",
    "[x #a][ref]\n\n[ref]: https://example.com",
])
def test_本文のタグにしないもの(body):
    assert body_tags(body) == []


def test_フェンスの後ろの本文は拾う():
    assert body_tags("```\n#x\n```\n#y") == ["y"]


# ---------- 描画との一致（body_tags == 本番の描画 render_markdown でできた a.inline-tag の名前） ----------

_RENDERED_TAG_RE = re.compile(r'<a href="[^"]*" class="inline-tag" title="「#([^」]*)」のノート一覧へ">')


def _rendered_tags(body):
    names = _RENDERED_TAG_RE.findall(render_markdown(body, published_only=False))
    return list(dict.fromkeys(names))


@pytest.mark.parametrize("body", [
    "# 見出し #a\n## #b 見出し",
    "- #a\n  - #b\n1. #c",
    "**#強調** *#e* ~~#s~~ **強調 #x**",
    "|a|b|\n|-|-|\n|#t1|#t2|\n|c|d #t3|",
    "> #q1\n>#q2\n> 本文 #q3",
    "> [!note] タイトル #t\n> 本文 #b",
    "```ad-note\ntitle: T\n#in-fence-body\n```\n#after",
    "```\n#code\n```\n#after",
    "~~~\n#code\n~~~",
    "    #include <x>\n\n#real",
    "`#inline` と `code`#tag と #ok",
    "\\#x と #y",
    "C# の話と PR #18 と #2024 と #2024年度",
    "日本語の文中に #タグ があり、#別タグ、#三つ目。#四つ目）#五つ目",
    "全角の句読点で切れる #a、#b。#c）#d」#e",
    "<!-- #hidden -->\n#shown",
    "<div>\n#in-html\n</div>\n\n#out",
    "数式 $a #b$ と $$\n#c\n$$ と #d",
    "[x #a][ref] と [y #b](https://example.com) と #c\n\n[ref]: https://example.com",
    "[[ノート#見出し]] と [[ノート #x|別名]] と ![[画像 #y.png]] と #z",
    "[[存在しないノート|メモ #重要]] と [[無い #見出し]] と #z",
    "https://example.com/#a と [x](#b) と <https://x.com/#c> と #d",
    "#a/b/ と #階層/タグ/ と #/ と #a-b_c",
    "- [ ] #todo\n- [x] #done",
    "",
    "タグなし",
])
def test_索引のタグは描画でタグの札になったものと一致する(body):
    assert body_tags(body) == _rendered_tags(body)


# ---------- frontmatter_tags ----------

@pytest.mark.parametrize("frontmatter, expected", [
    ({}, []),
    ({"tags": None}, []),
    ({"tags": "仕事"}, ["仕事"]),
    ({"tags": ["a", "b"]}, ["a", "b"]),
    ({"tags": ["#a", " #b "]}, ["a", "b"]),
    ({"tags": ["", "  ", None, "c"]}, ["c"]),
    ({"tags": 2024}, ["2024"]),
    ({"tags": [2024, "x"]}, ["2024", "x"]),
    (None, []),
    ("文字列", []),
    ([1, 2], []),
])
def test_frontmatterのタグの形(frontmatter, expected):
    assert frontmatter_tags(frontmatter) == expected


# ---------- note_tags ----------

def test_frontmatterのタグが先で本文のタグが後():
    assert note_tags({"tags": ["b", "a"]}, ["c", "a"]) == ["b", "a", "c"]


def test_同じタグは最初に出た1つだけ():
    assert note_tags({"tags": ["a"]}, ["a", "b", "b"]) == ["a", "b"]


def test_数値のタグと本文のタグが両方あっても落ちない():
    assert note_tags({"tags": 2024}, ["x"]) == ["2024", "x"]


# ---------- tag_href ----------

def test_tag_hrefは一覧の絞り込みへのURL():
    assert tag_href("議事録").startswith("/?tag=")
    assert tag_href("abc") == "/?tag=abc"


@pytest.mark.parametrize("ch, encoded", [("&", "%26"), ("#", "%23"), ("?", "%3F"), ("%", "%25"), ("+", "%2B"), (" ", "%20")])
def test_tag_hrefは壊れやすい文字をエンコードする(ch, encoded):
    assert tag_href(f"a{ch}b") == f"/?tag=a{encoded}b"


def test_tag_hrefは日本語をパーセントエンコードする():
    assert tag_href("会議") == "/?tag=%E4%BC%9A%E8%AD%B0"
