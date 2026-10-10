"""パスのスラッグ化（app/utils/slug.py）の契約テスト

記事の URL（/view/<スラッグ>）はこの変換で決まる。変わると既存の URL・共有済みのリンクが切れるので、
いまの変換結果をそのまま守る。
"""
import pytest

from app.utils.slug import slugify_path, slugify_segment


@pytest.mark.parametrize("text, expected", [
    ("日本語", "nihongo"),
    ("テスト仕様", "tesutoshiyou"),
    ("東京タワー", "toukyoutawaa"),
])
def test_日本語はヘボン式のローマ字にする(text, expected):
    assert slugify_segment(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Hello World", "hello-world"),
    ("ABC_def", "abc-def"),
    ("メモ (2025)", "memo-2025"),
])
def test_英字は小文字にし英数字以外の並びはハイフン1つにする(text, expected):
    assert slugify_segment(text) == expected


@pytest.mark.parametrize("text", ["---", "", "  "])
def test_英数字が残らなければ空文字(text):
    assert slugify_segment(text) == ""


def test_パスはmdを外して区切りごとに変換する():
    assert slugify_path("フォルダ/ノート.md") == "foruda/nooto"


def test_md以外の拡張子は外さない():
    assert slugify_path("note") == "note"
    assert slugify_path("x.md.md") == "x-md"


@pytest.mark.parametrize("path, expected", [
    ("a//b.md", "a/b"),
    ("/先頭/x.md", "sentou/x"),
])
def test_空の区切りは捨てる(path, expected):
    assert slugify_path(path) == expected
