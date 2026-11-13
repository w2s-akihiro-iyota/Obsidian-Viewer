"""frontmatter の読み取り（app/core/frontmatter.py）の契約テスト

- is_published: 外部に見せてよいノートかの判定。公開ノートの範囲を決めるので、True 以外を公開にしない
- parse_frontmatter: 先頭の --- で囲んだ YAML を辞書にし、残りを本文として返す。読めなければ本文をそのまま返す
- indexing と wikilinks は、どちらを先に読み込んでも循環しない（Q-13）
"""
import subprocess
import sys

import pytest

from app.core.frontmatter import frontmatter_strings, is_published, note_aliases, parse_frontmatter, read_frontmatter


# ---------- is_published ----------

@pytest.mark.parametrize("value", [True, "true", "True", "TRUE"])
def test_publishがtrueなら公開(value):
    assert is_published({"publish": value}) is True


@pytest.mark.parametrize("value", [False, "false", "yes", 1, "1", None, ""])
def test_publishがtrue以外なら非公開(value):
    assert is_published({"publish": value}) is False


def test_publishが無ければ非公開():
    assert is_published({}) is False
    assert is_published({"title": "x"}) is False


# ---------- parse_frontmatter ----------

def test_frontmatterを辞書にして本文と分ける():
    text = "---\ntitle: メモ\npublish: true\n---\n本文\n"
    assert parse_frontmatter(text) == ({"title": "メモ", "publish": True}, "本文\n")


def test_BOMとCRLFでも読む():
    text = "\ufeff---\r\ntags: [a]\r\n---\r\n本文"
    assert parse_frontmatter(text) == ({"tags": ["a"]}, "本文")


@pytest.mark.parametrize("text", ["本文だけ", "---\n閉じていない", "---\n: [壊れた YAML\n---\n本文"])
def test_frontmatterが無い_読めないときは本文をそのまま返す(text):
    meta, body = parse_frontmatter(text)
    assert meta == {} and body == text


# ---------- read_frontmatter（F-14・B-20） ----------

def test_ふつうのfrontmatterはerrorが空():
    r = read_frontmatter("---\ntitle: メモ\n---\n本文\n")
    assert (r.data, r.body, r.error) == ({"title": "メモ"}, "本文\n", "")


@pytest.mark.parametrize("text", ["---\n---\n本文", "---\n\n---\n本文", "---\r\n---\r\n本文"])
def test_空のfrontmatterは読めた扱いで本文は閉じの後ろ(text):
    r = read_frontmatter(text)
    assert (r.data, r.body, r.error) == ({}, "本文", "")


def test_frontmatterが無ければerrorも空():
    r = read_frontmatter("本文だけ")
    assert (r.data, r.body, r.error) == ({}, "本文だけ", "")


@pytest.mark.parametrize("prefix, leading_lines", [("", 0), ("\ufeff", 0), ("\n\n", 2), ("\ufeff\n", 1)])
def test_YAMLの誤りはファイル全体での行番号を返す(prefix, leading_lines):
    # 開きの --- の次の次の行（YAML の 2 行目）が誤り
    text = prefix + "---\na: 1\nb: : :\n---\n本文"
    r = read_frontmatter(text)
    assert r.data == {} and r.body == text.lstrip("\ufeff")
    assert r.error == f"YAML の書き方の誤り（{leading_lines + 3} 行目）"


def test_閉じの線が無ければそう言う():
    r = read_frontmatter("---\ntitle: x\n本文")
    assert (r.data, r.body, r.error) == ({}, "---\ntitle: x\n本文", "閉じの --- が無い")


@pytest.mark.parametrize("yaml_text", ["ただの文字列", "- a\n- b", "42", "0", "false"])
def test_辞書でないfrontmatterはdataが空で本文は閉じの後ろ(yaml_text):
    r = read_frontmatter(f"---\n{yaml_text}\n---\n本文")
    assert (r.data, r.body, r.error) == ({}, "本文", "key: value の形になっていない")
    assert parse_frontmatter(f"---\n{yaml_text}\n---\n本文") == ({}, "本文")


@pytest.mark.parametrize("text", ["----------\n本文", "--- メモ ---\n本文\n---", "-----\nあ\n-----\n", "---x\n本文"])
def test_区切り線で始まる本文はfrontmatterではない(text):
    r = read_frontmatter(text)
    assert (r.data, r.body, r.error) == ({}, text, "")


@pytest.mark.parametrize("text", ["---", "---\n", "\n---  \n\n"])
def test_区切り線1本だけのノートはfrontmatterではない(text):
    r = read_frontmatter(text)
    assert (r.data, r.body, r.error) == ({}, text, "")


@pytest.mark.parametrize("text", ["---  \ntitle: x\n---\n本文", "\n \n---\ntitle: x\n---\n本文"])
def test_開きの後ろの空白と手前の空行は許す(text):
    r = read_frontmatter(text)
    assert (r.data, r.body, r.error) == ({"title": "x"}, "本文", "")


# ---------- frontmatter_strings ----------

@pytest.mark.parametrize("value, expected", [
    (None, []),
    ("a", ["a"]),
    (2024, ["2024"]),
    (["a", " b ", "", None, "a", 1], ["a", "b", "1"]),
    ([{"a": 1}, ["x"], "ok"], ["ok"]),
    ({"a": 1}, []),
    ("  ", []),
])
def test_frontmatterの値を文字列のリストにする(value, expected):
    assert frontmatter_strings(value) == expected


# ---------- note_aliases（X-2） ----------

@pytest.mark.parametrize("frontmatter, expected", [
    ({}, []),
    ({"aliases": None}, []),
    ({"aliases": "別名"}, ["別名"]),
    ({"aliases": ["a", " b ", "", None, "a"]}, ["a", "b"]),
    ({"aliases": 2024}, ["2024"]),
    ({"aliases": [1, "1"]}, ["1"]),
    ({"aliases": "  "}, []),
    ({"aliases": [{"a": 1}, "b"]}, ["b"]),
])
def test_別名はどんな形でも文字列の一覧にする(frontmatter, expected):
    assert note_aliases(frontmatter) == expected


# ---------- 読み込みの順 ----------

@pytest.mark.parametrize("modules", [
    ("app.services.wikilinks", "app.core.indexing"),
    ("app.core.indexing", "app.services.wikilinks"),
])
def test_indexingとwikilinksはどちらを先に読み込んでも循環しない(modules):
    # 読み込み済みのモジュールに左右されないよう、別のプロセスで読み込む
    code = "; ".join(f"import {m}" for m in modules)
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
