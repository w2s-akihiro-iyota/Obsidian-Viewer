"""frontmatter の読み取り（app/core/frontmatter.py）の契約テスト

- is_published: 外部に見せてよいノートかの判定。公開ノートの範囲を決めるので、True 以外を公開にしない
- parse_frontmatter: 先頭の --- で囲んだ YAML を辞書にし、残りを本文として返す。読めなければ本文をそのまま返す
- indexing と wikilinks は、どちらを先に読み込んでも循環しない（Q-13）
"""
import subprocess
import sys

import pytest

from app.core.frontmatter import is_published, parse_frontmatter


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
    text = "﻿---\r\ntags: [a]\r\n---\r\n本文"
    assert parse_frontmatter(text) == ({"tags": ["a"]}, "本文")


@pytest.mark.parametrize("text", ["本文だけ", "---\n閉じていない", "---\n: [壊れた YAML\n---\n本文"])
def test_frontmatterが無い_読めないときは本文をそのまま返す(text):
    meta, body = parse_frontmatter(text)
    assert meta == {} and body == text


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
