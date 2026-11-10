"""全文検索のトークン化（app/core/search.py）の契約テスト

索引と検索語は同じ tokenize で切る。切り方が変わると、索引を作り直すまで検索が当たらなくなる。
- NFKC で正規化してから切る（全角英数字は半角、半角カナは全角にそろう。B-13）
- 英数字（アクセント付きの文字も含む）と _ は単語で切って小文字にする
- 日本語（ひらがな・カタカナ・漢字）は 2 文字ずつずらして切る（1 文字だけならその 1 文字）
"""
import unicodedata
from itertools import groupby

import pytest

from app.core.search import META_WEIGHT, SearchIndex, _is_cjk, frontmatter_search_text, tokenize, tokenize_query


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


# ---------- tokenize の高速化（Q-20）：切り方は変えない ----------

def _reference_tokenize(text: str) -> list[str]:
    """Q-20 前の tokenize（1 文字ずつ種類を判定する実装）。正規表現版と出力が同じであることの基準"""
    def kind(ch):
        if _is_cjk(ch):
            return "cjk"
        if ch.isalnum() or ch == "_":
            return "word"
        return None

    tokens = []
    for k, chars in groupby(unicodedata.normalize("NFKC", text).lower(), key=kind):
        if k == "word":
            tokens.append("".join(chars))
        elif k == "cjk":
            s = "".join(chars)
            if len(s) == 1:
                tokens.append(s)
            else:
                tokens.extend(s[j:j + 2] for j in range(len(s) - 1))
    return tokens


_TOKENIZE_SAMPLES = [
    "", " ", "Hello World", "foo_bar-baz", "日本語", "ラーメン", "日", "日本語text混在テスト123",
    "Ｐｌａｙｗｒｉｇｈｔ　ＡＢＣ１２３", "ﾊﾝｶｸｶﾅ", "café naïve Zürich", "😀絵文字😀emoji🎉テスト", "㍿ ㌔ ㈱",
    "가나다 한글", "α β γ", "①②③ ⅷ", "a.b,c;d", "豈 㐀 ー々〆", "é combining", "snake_case_名前_x",
    "# 見出し\n- リスト `code` [[リンク|別名]]", "ＡＩ（人工知能）とLLM、E2Eテスト", "ǅ ß İ ı", "٣٤ ४५", "𠮷野家 𩸽",
]


@pytest.mark.parametrize("text", _TOKENIZE_SAMPLES)
def test_tokenizeはQ20前の実装と出力が同じ(text):
    assert tokenize(text) == _reference_tokenize(text)


def test_tokenizeはランダムな文字列でもQ20前の実装と同じ():
    import random

    rng = random.Random(20)
    pool = [chr(c) for c in range(0x20, 0x3000)] + [chr(c) for c in range(0xf900, 0xfb00)] \
        + [chr(c) for c in range(0xff00, 0xfff0)] + ["😀", "𠮷", "́"]
    for _ in range(3000):
        text = "".join(rng.choice(pool) for _ in range(rng.randint(1, 12)))
        assert tokenize(text) == _reference_tokenize(text), repr(text)


# ---------- frontmatter でも当たる（F-13） ----------

def _entry(path, title="", body="", **frontmatter):
    return {"path": path, "title": title or path, "body_text": body, "published": True,
            "tags": [], "frontmatter": frontmatter}


def _pad(n=3):
    """語が全ノートに出ると idf が 0 になるので、無関係なノートを足す"""
    return [_entry(f"pad{i}.md", f"p{i}", "他") for i in range(n)]


def _search(files, query, is_localhost=True):
    idx = SearchIndex()
    idx.build(files)
    return idx.search(query, is_localhost, files)


def test_メタ情報の重みはタイトルより下で本文より上():
    assert 1.0 < META_WEIGHT < 3.0


def test_keywordsにだけある語で検索するとそのノートが出る():
    files = [
        _entry("a.md", "Playwright入門", "ブラウザの自動操作について", keywords=["Playwright", "プレイライト", "E2E"]),
        _entry("b.md", "別のノート", "関係ない本文"),
    ]
    assert [r["path"] for r in _search(files, "プレイライト")] == ["a.md"]
    assert [r["path"] for r in _search(files, "e2e")] == ["a.md"]


@pytest.mark.parametrize("key", ["keywords", "summary", "description", "aliases"])
def test_検索の対象はkeywords_summary_description_aliases(key):
    files = [_entry("a.md", "題", "本文", **{key: "ユニークワード"}), _entry("b.md", "題2", "本文")]
    assert [r["path"] for r in _search(files, "ユニークワード")] == ["a.md"]


def test_メタ情報は文字列でも配列でも数値でも扱える():
    assert frontmatter_search_text({"keywords": "a, b", "aliases": ["x", 2024], "summary": 5}) == "a, b 5 x 2024"


@pytest.mark.parametrize("frontmatter", [None, [], "壊れた", 3, {}, {"keywords": None}, {"keywords": [None, ""]}])
def test_メタ情報が無い_壊れているときは空として扱う(frontmatter):
    assert frontmatter_search_text(frontmatter).strip() == ""


def test_メタ情報の当たりは本文より強くタイトルより弱い():
    word = "ゼータ"
    files = [
        _entry("body.md", "x", word),
        _entry("meta.md", "x", "", keywords=[word]),
        _entry("title.md", word, ""),
        _entry("pad1.md", "p1", "他"), _entry("pad2.md", "p2", "他"), _entry("pad3.md", "p3", "他"),
    ]
    scores = {r["path"]: r["score"] for r in _search(files, word)}
    assert scores["body.md"] < scores["meta.md"] < scores["title.md"]


def test_抜粋は本文に当たりが無ければsummaryを出す():
    files = [_entry("a.md", "題", "全然関係のない本文" * 5, summary="これは要約です", description="説明", keywords=["要約語"])] + _pad()
    assert _search(files, "要約語")[0]["snippet"] == "これは要約です"


def test_抜粋はsummaryが無ければdescriptionを出す():
    files = [_entry("a.md", "題", "全然関係のない本文", description="これは説明です", keywords=["説明語"])] + _pad()
    assert _search(files, "説明語")[0]["snippet"] == "これは説明です"


def test_本文に当たりがあれば抜粋は本文から出す():
    files = [_entry("a.md", "題", "ここに検索語ABCがある", summary="要約")] + _pad()
    assert "ABC" in _search(files, "ABC")[0]["snippet"]


def test_外部の人には公開ノートだけを返す_メタ情報でも():
    pub = _entry("pub.md", "公", "本文", keywords=["秘密語"])
    priv = _entry("priv.md", "非", "本文", keywords=["秘密語"])
    priv["published"] = False
    assert [r["path"] for r in _search([pub, priv] + _pad(), "秘密語", is_localhost=False)] == ["pub.md"]
    assert {r["path"] for r in _search([pub, priv] + _pad(), "秘密語", is_localhost=True)} == {"pub.md", "priv.md"}


def test_変わっていないノートのトークンは前回のものを使い回す(monkeypatch):
    from app.core import search

    files = [_entry("a.md", "題", "本文テキスト", keywords=["k1"]), _entry("b.md", "題b", "別の本文")]
    first = SearchIndex()
    first.build(files)
    calls = []
    original = search.tokenize
    monkeypatch.setattr(search, "tokenize", lambda t: calls.append(t) or original(t))
    files[1] = _entry("b.md", "題b", "書き換えた本文")
    second = SearchIndex()
    second.build(files, previous=first)
    assert "本文テキスト" not in calls and "別の本文" not in calls   # a は使い回し
    assert "書き換えた本文" in calls                                   # b は切り直し
    assert [r["path"] for r in second.search("書き換えた", True, files)] == ["b.md"]
    assert [r["path"] for r in second.search("k1", True, files)] == ["a.md"]
