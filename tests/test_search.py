"""全文検索のトークン化（app/core/search.py）の契約テスト

索引と検索語は同じ tokenize で切る。切り方が変わると、索引を作り直すまで検索が当たらなくなる。
- NFKC で正規化してから切る（全角英数字は半角、半角カナは全角にそろう。B-13）
- 英数字（アクセント付きの文字も含む）と _ は単語で切って小文字にする
- 日本語（ひらがな・カタカナ・漢字）は 2 文字ずつずらして切る（1 文字だけならその 1 文字）
"""
import pytest

from app.core.search import SearchIndex, _is_cjk, tokenize, tokenize_query


@pytest.mark.parametrize("ch", ["あ", "ア", "ー", "漢", "㐀", "豈"])
def test_ひらがなカタカナ漢字は日本語の文字(ch):
    assert _is_cjk(ch)


@pytest.mark.parametrize("ch", ["a", "1", " ", "、", "。", "Ａ", "é", "가"])
def test_英数字や記号や全角英字やハングルは日本語の文字でない(ch):
    assert not _is_cjk(ch)


def test_英単語は小文字の単語に切る():
    assert tokenize("Hello World") == ["hello", "world"]


def test_アンダースコアは単語に含めハイフンでは切る():
    assert tokenize("foo_bar-baz") == ["foo_bar", "baz"]


def test_日本語は2文字ずつずらして切る():
    assert tokenize("日本語") == ["日本", "本語"]
    assert tokenize("ラーメン") == ["ラー", "ーメ", "メン"]


def test_日本語が1文字だけならその1文字():
    assert tokenize("日") == ["日"]


def test_英字と日本語が続くときは種類の変わり目で切る():
    assert tokenize("Python入門ガイド") == ["python", "入門", "門ガ", "ガイ", "イド"]


def test_句読点で日本語の並びを区切る():
    assert tokenize("あ、い") == ["あ", "い"]


def test_空文字は空():
    assert tokenize("") == []


def test_全角英数字は半角にそろえて単語に切る():
    assert tokenize("ＡＢＣ１２３") == ["abc123"]
    assert tokenize("ＡＢＣ") == tokenize("abc")


def test_アクセント付きの文字は単語に含める():
    assert tokenize("café crème") == ["café", "crème"]


def test_半角カナは全角にそろえて2文字ずつ切る():
    assert tokenize("ｶﾀｶﾅ") == tokenize("カタカナ") == ["カタ", "タカ", "カナ"]


def test_全角英字と日本語が続くときも種類の変わり目で切る():
    assert tokenize("Ｐｙｔｈｏｎ入門") == ["python", "入門"]


@pytest.mark.parametrize("text", ["Hello 世界", "日本語の検索", "abc_123 テスト"])
def test_検索語は索引と同じ切り方をする(text):
    assert tokenize_query(text) == tokenize(text)


@pytest.mark.parametrize("query", ["abc", "ＡＢＣ", "Abc"])
def test_全角と半角のどちらで探しても当たる(query):
    files = [{"path": "全角.md", "title": "メモ", "body_text": "型番はＡＢＣです", "tags": [], "published": True},
             {"path": "半角.md", "title": "メモ", "body_text": "型番はabcです", "tags": [], "published": True},
             # 全部のノートに出る語は IDF が 0 で当たらないので、含まないノートも置く
             {"path": "別.md", "title": "メモ", "body_text": "型番はxyzです", "tags": [], "published": True}]
    idx = SearchIndex()
    idx.build(files)
    assert sorted(r["path"] for r in idx.search(query, True, files)) == ["全角.md", "半角.md"]
