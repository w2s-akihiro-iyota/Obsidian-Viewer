"""索引作り（app/core/indexing.py）の小さな関数の契約テスト

- scan_notes: 更新日時は JST（コンテナは UTC。B-9）
"""
import os
import threading
from datetime import datetime
from pathlib import Path

import pytest

from app.core.indexing import scan_notes


# ---------- scan_notes ----------

def test_更新日時はJSTで持つ(tmp_path):
    note = tmp_path / "ノート.md"
    note.write_text("本文", encoding="utf-8")
    # UTC 2026-10-10 20:30 = JST 2026-10-11 05:30（タイムゾーンなしだとコンテナでは前日になる）
    ts = datetime.fromisoformat("2026-10-10T20:30:00+00:00").timestamp()
    os.utime(note, (ts, ts))
    mtime = scan_notes(tmp_path, tmp_path)[0].mtime
    assert mtime.strftime("%Y-%m-%d %H:%M") == "2026-10-11 05:30"
    assert mtime.utcoffset().total_seconds() == 9 * 3600


# ---------- NoteResolver に渡す Vault のパス（F-11） ----------

def test_索引の作り直しは同期元の対応表からVaultのパスを渡す(monkeypatch):
    from app.core import content_sources, indexing
    from app.core.note_resolver import NoteResolver

    class FakeSources:
        @staticmethod
        def vault_path(view_path):
            return f"notes/{view_path}" if not view_path.startswith("llm-wiki/") else view_path

    monkeypatch.setattr(content_sources.ContentSources, "from_config", classmethod(lambda cls, config: FakeSources()))
    monkeypatch.setattr("app.services.sync_config.load_config", lambda: None)
    entries = indexing._resolver_entries([{"path": "a/b.md"}, {"path": "llm-wiki/x.md"}])
    assert entries == [("a/b.md", "notes/a/b.md"), ("llm-wiki/x.md", "llm-wiki/x.md")]
    assert NoteResolver(entries).resolve("notes/a/b") == "a/b.md"


# ---------- 変わっていないノートは読み直さない（Q-20） ----------

def _write(path, text, ts=None):
    path.write_text(text, encoding="utf-8")
    if ts is not None:
        os.utime(path, (ts, ts))


def _count_opens(monkeypatch):
    """scan_notes がノートのファイルを開いた回数のカウンタ"""
    from app.core import indexing

    opened = []
    real_open = open

    def counting_open(file, *args, **kwargs):
        if str(file).endswith(".md"):
            opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(indexing, "open", counting_open, raising=False)
    return opened


def test_変わっていないノートは読み直さず前回の記録をそのまま使う(tmp_path, monkeypatch):
    _write(tmp_path / "a.md", "---\ntitle: A\n---\n本文", 1_700_000_000)
    _write(tmp_path / "b.md", "本文b", 1_700_000_000)
    previous = {n.rel_path: n for n in scan_notes(tmp_path, tmp_path)}
    opened = _count_opens(monkeypatch)
    second = scan_notes(tmp_path, tmp_path, previous=previous)
    assert opened == []
    assert {n.rel_path: n for n in second}["a.md"] is previous["a.md"]


def test_本文のタグは変わっていないノートでは再計算しない(tmp_path, monkeypatch):
    from app.core import indexing

    _write(tmp_path / "a.md", "#a の本文", 1_700_000_000)
    _write(tmp_path / "b.md", "#b の本文", 1_700_000_000)
    previous = {n.rel_path: n for n in scan_notes(tmp_path, tmp_path)}
    assert previous["a.md"].body_tags == ("a",)
    calls = []
    real = indexing.body_tags
    monkeypatch.setattr(indexing, "body_tags", lambda body: calls.append(body) or real(body))
    _write(tmp_path / "b.md", "#c に変えた", 1_700_000_100)
    notes = {n.rel_path: n for n in scan_notes(tmp_path, tmp_path, previous=previous)}
    assert calls == ["#c に変えた"]
    assert notes["a.md"].body_tags == ("a",) and notes["b.md"].body_tags == ("c",)


def test_変わったノートだけ読み直す(tmp_path, monkeypatch):
    _write(tmp_path / "a.md", "古い", 1_700_000_000)
    _write(tmp_path / "b.md", "そのまま", 1_700_000_000)
    previous = {n.rel_path: n for n in scan_notes(tmp_path, tmp_path)}
    _write(tmp_path / "a.md", "新しい本文", 1_700_000_100)
    opened = _count_opens(monkeypatch)
    notes = {n.rel_path: n for n in scan_notes(tmp_path, tmp_path, previous=previous)}
    assert [Path(p).name for p in opened] == ["a.md"]
    assert notes["a.md"].body == "新しい本文"
    assert notes["b.md"] is previous["b.md"]


def test_更新日時が同じでもサイズが違えば読み直す(tmp_path):
    _write(tmp_path / "a.md", "abc", 1_700_000_000)
    previous = {n.rel_path: n for n in scan_notes(tmp_path, tmp_path)}
    _write(tmp_path / "a.md", "abcdef", 1_700_000_000)
    assert scan_notes(tmp_path, tmp_path, previous=previous)[0].body == "abcdef"


def test_消えたノートは結果から消え新しいノートは読む(tmp_path):
    _write(tmp_path / "a.md", "a", 1_700_000_000)
    _write(tmp_path / "b.md", "b", 1_700_000_000)
    previous = {n.rel_path: n for n in scan_notes(tmp_path, tmp_path)}
    (tmp_path / "a.md").unlink()
    _write(tmp_path / "c.md", "c", 1_700_000_000)
    notes = scan_notes(tmp_path, tmp_path, previous=previous)
    assert sorted(n.rel_path for n in notes) == ["b.md", "c.md"]


def test_statは1件につき1回まで(tmp_path, monkeypatch):
    from app.core import indexing

    for name in "abc":
        _write(tmp_path / f"{name}.md", name, 1_700_000_000)
    previous = {n.rel_path: n for n in scan_notes(tmp_path, tmp_path)}
    stats = []
    real_stat = os.stat

    def counting_stat(path, *args, **kwargs):
        if str(path).endswith(".md"):
            stats.append(str(path))
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(indexing.os, "stat", counting_stat)
    scan_notes(tmp_path, tmp_path, previous=previous)
    assert len(stats) == 3 and len(set(stats)) == 3


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch, isolated_caches):
    from app.core import indexing

    monkeypatch.setattr(indexing, "CONTENT_DIR", tmp_path)
    monkeypatch.setattr(indexing, "MEDIA_DIR", tmp_path.parent / f"{tmp_path.name}-media")
    return tmp_path


def test_作り直しが成功したら前回の記録を差し替える(isolated_cache):
    from app import cache
    from app.core import indexing

    _write(isolated_cache / "a.md", "a", 1_700_000_000)
    indexing.refresh_global_caches()
    assert set(cache.NOTE_RECORDS) == {"a.md"}
    _write(isolated_cache / "b.md", "b", 1_700_000_000)
    indexing.refresh_global_caches()
    assert set(cache.NOTE_RECORDS) == {"a.md", "b.md"}


def test_作り直しが途中で失敗したら前回の記録を壊さない(isolated_cache, monkeypatch):
    from app import cache
    from app.core import indexing, search

    _write(isolated_cache / "a.md", "a", 1_700_000_000)
    indexing.refresh_global_caches()
    before = cache.NOTE_RECORDS
    _write(isolated_cache / "b.md", "b", 1_700_000_000)

    def boom(self, *args, **kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr(search.SearchIndex, "build", boom)
    with pytest.raises(RuntimeError):
        indexing.refresh_global_caches()
    assert cache.NOTE_RECORDS is before and set(before) == {"a.md"}


def test_変わっていないノートでも作り直しのあと検索が当たる(isolated_cache):
    from app import cache
    from app.core import indexing

    _write(isolated_cache / "a.md", "---\nkeywords: [プレイライト]\n---\n本文", 1_700_000_000)
    for name in "bcd":   # 語が全ノートに出ると idf が 0 になるので、無関係なノートを足す
        _write(isolated_cache / f"{name}.md", "他", 1_700_000_000)
    indexing.refresh_global_caches()
    indexing.refresh_global_caches()
    res = cache.SEARCH_INDEX.search("プレイライト", True, cache.GLOBAL_FILE_CACHE)
    assert [r["path"] for r in res] == ["a.md"]


# ---------- バックグラウンドの作り直し（Q-20）: 同時に 1 本、走っている間の依頼は終わったあと 1 回にまとめる ----------

def test_走っている間に何度頼んでも終わったあとに1回だけ走る(monkeypatch):
    from app.core import indexing

    calls = []
    release = threading.Event()
    started = threading.Event()

    def fake_refresh():
        calls.append(1)
        started.set()
        release.wait(5)

    monkeypatch.setattr(indexing, "refresh_global_caches", fake_refresh)
    indexing.schedule_background_refresh()
    assert started.wait(5)
    for _ in range(5):
        indexing.schedule_background_refresh()
    release.set()
    assert indexing.background_refresher.wait_idle(5)
    assert len(calls) == 2


def test_バックグラウンドの作り直しが失敗してもログに残して次を受け付ける(monkeypatch, caplog):
    from app.core import indexing

    calls = []

    def fake_refresh():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("fail")

    monkeypatch.setattr(indexing, "refresh_global_caches", fake_refresh)
    with caplog.at_level("ERROR", logger="app.indexing"):
        indexing.schedule_background_refresh()
        assert indexing.background_refresher.wait_idle(5)
    assert any(r.levelname == "ERROR" for r in caplog.records)
    indexing.schedule_background_refresh()
    assert indexing.background_refresher.wait_idle(5)
    assert len(calls) == 2


# ---------- 形の変な frontmatter（B-20）・読めない理由（F-14）・別名（X-2） ----------

def test_辞書でないfrontmatterが混じっても索引は最後まで作れる(isolated_cache):
    from app import cache
    from app.core import indexing

    _write(isolated_cache / "普通.md", "---\npublish: true\ntags: [a]\n---\n本文")
    _write(isolated_cache / "文字列.md", "---\nただの文字列\n---\n本文")
    _write(isolated_cache / "リスト.md", "---\n- a\n- b\n---\n本文")
    _write(isolated_cache / "数値.md", "---\n42\n---\n本文")
    _write(isolated_cache / "壊れ.md", "---\na: 1\nb: : :\n---\n本文")
    _write(isolated_cache / "閉じ無し.md", "---\ntitle: x\n本文")
    indexing.refresh_global_caches()
    files = {f["path"]: f for f in cache.GLOBAL_FILE_CACHE}
    assert set(files) == {"普通.md", "文字列.md", "リスト.md", "数値.md", "壊れ.md", "閉じ無し.md"}
    assert files["普通.md"]["published"] and "a" in files["普通.md"]["tags"]
    assert files["普通.md"]["frontmatter_error"] == ""
    for name in ("文字列.md", "リスト.md", "数値.md"):
        assert files[name]["frontmatter_error"] == "key: value の形になっていない"
        assert files[name]["frontmatter"] == {} and not files[name]["published"]
    assert files["壊れ.md"]["frontmatter_error"] == "YAML の書き方の誤り（3 行目）"
    assert files["閉じ無し.md"]["frontmatter_error"] == "閉じの --- が無い"


def test_別名のリンクは索引の作り直しでつながる(isolated_cache):
    from app import cache
    from app.core import indexing

    _write(isolated_cache / "定例.md", "---\naliases: [週次, 'ミーティング']\n---\n本文")
    _write(isolated_cache / "参照元.md", "[[週次]] と [[ミーティング]] と [[無い]]")
    indexing.refresh_global_caches()
    assert cache.NOTE_RESOLVER.resolve("週次") == "定例.md"
    assert cache.FORWARD_LINK_CACHE["参照元.md"] == ["定例.md"]
    assert {f["path"]: f["missing_links"] for f in cache.GLOBAL_FILE_CACHE}["参照元.md"] == ["無い"]
