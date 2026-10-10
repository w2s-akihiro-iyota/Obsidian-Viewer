"""索引作り（app/core/indexing.py）の小さな関数の契約テスト

- is_published: 外部に見せてよいノートかの判定。公開ノートの範囲を決めるので、True 以外を公開にしない
- parse_obsidian_date: 日付の文字列を datetime にする
"""
from datetime import datetime

import pytest

from app.core.indexing import is_published, parse_obsidian_date


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


# ---------- parse_obsidian_date ----------

@pytest.mark.parametrize("value", [None, "", 0])
def test_日付が空ならNone(value):
    assert parse_obsidian_date(value) is None


def test_datetimeはそのまま返す():
    dt = datetime(2025, 3, 4, 16, 3, 46)
    assert parse_obsidian_date(dt) is dt


# 以下は文字列を渡したときの期待。いまの実装は isinstance(date_str, (datetime, datetime.date)) の
# datetime.date が型ではない（datetime クラスのメソッド）ため、文字列を渡すと TypeError になる（不具合候補）。
# 直ったら xfail を外し、期待どおりかを確かめる。
_TYPE_ERROR = pytest.mark.xfail(raises=TypeError, strict=True,
                                reason="indexing.py:43 datetime.date が型でなく、文字列で TypeError になる")


@_TYPE_ERROR
@pytest.mark.parametrize("text, expected", [
    ("2025-03-04 16:03:46", datetime(2025, 3, 4, 16, 3, 46)),
    ("2025-03-04 16:03", datetime(2025, 3, 4, 16, 3)),
    ("2025-03-04T16:03:46", datetime(2025, 3, 4, 16, 3, 46)),
    ("2025-03-04", datetime(2025, 3, 4)),
    ("  2025-03-04  ", datetime(2025, 3, 4)),
])
def test_ISO形式の日付を読む(text, expected):
    assert parse_obsidian_date(text) == expected


# Obsidian の日本語ロケールが frontmatter に書く形式（旧 debug/debug_date_parse.py のサンプル）。
# いまの実装はこの形式の書式を持たない（TypeError を直しても None になる）。対応するまでは xfail で残す。
# いまは TypeError で落ちるが、書式の対応が済むまでは何で落ちても xfail のままにする（raises を絞らない）。
@pytest.mark.xfail(strict=True, reason="未対応の書式。ロードマップ Q-18")
@pytest.mark.parametrize("text, expected", [
    ("火曜日, 3月 4日 2025, 4:03:46 午後", datetime(2025, 3, 4, 16, 3, 46)),
    ("水曜日, 4月 16日 2025, 12:35:46 午後", datetime(2025, 4, 16, 12, 35, 46)),
    ("木曜日, 4月 24日 2025, 9:55:24 午前", datetime(2025, 4, 24, 9, 55, 24)),
    ("火曜日, 2月 13日 2024, 12:24:35 午後", datetime(2024, 2, 13, 12, 24, 35)),
])
def test_Obsidianの日本語の日付を読む(text, expected):
    assert parse_obsidian_date(text) == expected
