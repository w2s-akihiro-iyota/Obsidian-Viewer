"""同期の記録（F-7）の契約テスト

- 追加（コピー先に無かった）と更新（コピー先にあった）を分けて数える
- 同期 1 回ごとに、開始時刻・秒数・成否・エラー・種類ごとの追加/更新/削除・保留・きっかけを残す
- 直近 SYNC_HISTORY_LIMIT 回だけ残す。ファイル名は種類ごとに SYNC_HISTORY_FILE_LIMIT 件まで（件数は全件）
- 記録が壊れていたら空として扱う
- 保留した削除を「確認して削除する」で消したときは、別の 1 回として残す
- 記録の API は管理者だけ
"""
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import sync_history
from app.main import app
from app.services import sync

ADMIN = "http://localhost:8001"
PUBLIC = "http://localhost:8000"


def _write(path: Path, text: str, mtime: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


@pytest.fixture
def env(tmp_path, monkeypatch):
    """同期元・コピー先を tmp_path に向ける（本物の Vault には触れない。記録ファイルは conftest.py で tmp_path に向けている）"""
    src, content, images = tmp_path / "vault", tmp_path / "content", tmp_path / "images"
    for d in (src, content, images):
        d.mkdir()
    monkeypatch.setattr(sync, "CONTENT_DIR", content)
    monkeypatch.setattr(sync, "IMAGES_DIR", images)
    monkeypatch.setattr(sync, "_pending", {})
    monkeypatch.setattr(sync, "refresh_global_caches", lambda: None)
    monkeypatch.setattr(sync, "save_config", lambda config: None)
    return src, content


def _config(src: Path, **kwargs) -> sync.SyncConfig:
    return sync.SyncConfig(sync_enabled=True, content_src=str(src), **kwargs)


def _history() -> list[dict]:
    return [r.model_dump() for r in sync_history.get_history()]


def _latest() -> dict:
    return _history()[0]


def _files(record: dict, change: str, kind: str = "content") -> list[str]:
    return record["kinds"][kind][change]["files"]


# ---------- 追加と更新の振り分け ----------

def test_コピー先に無ければ追加あれば更新(env):
    src, content = env
    _write(src / "既存.md", "v1")
    sync.sync_directory(src, content, [])
    _write(src / "既存.md", "version2", mtime=time.time() + 10)
    _write(src / "会議" / "新規.md", "new")
    result = sync.sync_directory(src, content, [])
    assert result.added == ["会議/新規.md"]
    assert result.updated == ["既存.md"]
    assert result.copied == 2


def test_同期の記録に追加更新削除のファイルを相対パスで残す(env):
    src, content = env
    for name in ("a.md", "b.md", "c.md"):
        _write(src / name, "x")
    sync.perform_sync(_config(src))
    _write(src / "a.md", "changed", mtime=time.time() + 10)
    (src / "b.md").unlink()
    _write(src / "フォルダ" / "d.md", "d")
    ok, _ = sync.perform_sync(_config(src))

    record = _latest()
    assert ok and record["ok"] and record["error"] == ""
    assert _files(record, "added") == ["フォルダ/d.md"]
    assert _files(record, "updated") == ["a.md"]
    assert _files(record, "deleted") == ["b.md"]
    assert record["kinds"]["content"]["added"]["count"] == 1
    assert record["trigger"] == "manual"
    assert record["duration_sec"] >= 0
    assert len(record["started_at"]) == len("2026-10-10 10:00:00")


def test_画像も種類を分けて残す(env, tmp_path):
    src, _ = env
    img_src = tmp_path / "img_src"
    _write(src / "a.md", "x")
    _write(img_src / "pic.png", "png")
    sync.perform_sync(_config(src, images_src=str(img_src)))
    record = _latest()
    assert _files(record, "added", "images") == ["pic.png"]
    assert _files(record, "added") == ["a.md"]


def test_自動同期はきっかけを自動として残す(env):
    src, _ = env
    _write(src / "a.md", "x")
    sync.perform_sync(_config(src), sync_history.SyncTrigger.AUTO)
    assert _latest()["trigger"] == "auto"


# ---------- 失敗も残す ----------

def test_同期元が見つからなければ失敗として残す(env, tmp_path):
    ok, message = sync.perform_sync(_config(tmp_path / "nowhere"))
    record = _latest()
    assert not ok and not record["ok"]
    assert record["error"] == message and message


def test_途中で例外が出ても失敗とエラー内容を残す(env, monkeypatch):
    src, _ = env
    _write(src / "a.md", "x")

    def broken(*args):
        raise RuntimeError("ディスクがいっぱい")

    monkeypatch.setattr(sync, "refresh_global_caches", broken)
    ok, _ = sync.perform_sync(_config(src))
    record = _latest()
    assert not ok and not record["ok"]
    assert "ディスクがいっぱい" in record["error"]
    assert _files(record, "added") == ["a.md"]   # 失敗するまでにコピーした分は残す


def test_同期が無効なら記録しない(env, tmp_path):
    sync.perform_sync(sync.SyncConfig(sync_enabled=False, content_src=str(tmp_path)))
    assert sync_history.get_history() == []


# ---------- 件数と上限 ----------

def test_直近10回だけ残し古いものから消える(env):
    src, _ = env
    _write(src / "a.md", "x")
    for _ in range(sync_history.SYNC_HISTORY_LIMIT + 2):
        sync.perform_sync(_config(src))
    history = _history()
    assert len(history) == sync_history.SYNC_HISTORY_LIMIT
    # 新しい順。最初の 1 回（a.md を追加した回）は消えている
    assert all(r["kinds"]["content"]["added"]["count"] == 0 for r in history)


def test_ファイル名は上限までで件数は全件残す(env, monkeypatch):
    src, _ = env
    monkeypatch.setattr(sync_history, "SYNC_HISTORY_FILE_LIMIT", 3)
    for i in range(5):
        _write(src / f"n{i}.md", "x")
    sync.perform_sync(_config(src))
    added = _latest()["kinds"]["content"]["added"]
    assert added["count"] == 5 and len(added["files"]) == 3


def test_保留した削除の件数と理由を残す(env):
    src, content = env
    for i in range(4):
        _write(src / f"n{i}.md", "x")
    sync.perform_sync(_config(src))
    for i in range(3):
        (src / f"n{i}.md").unlink()
    sync.perform_sync(_config(src))
    record = _latest()
    assert record["held"][0]["kind"] == "content"
    assert record["held"][0]["count"] == 3 and record["held"][0]["reason"]
    assert _files(record, "deleted") == []


# ---------- 壊れた記録 ----------

@pytest.mark.parametrize("text", ["{壊れている", '{"not": "list"}', ""])
def test_壊れた記録は空として扱い次の同期で作り直す(env, text):
    src, _ = env
    path = sync_history.SYNC_HISTORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    assert sync_history.get_history() == []
    _write(src / "a.md", "x")
    sync.perform_sync(_config(src))
    assert len(json.loads(path.read_text(encoding="utf-8"))) == 1


def test_形の合わない記録は1件ずつ捨てる(env):
    path = sync_history.SYNC_HISTORY_FILE
    good = {"started_at": "2026-10-10 10:00:00", "duration_sec": 1.0, "trigger": "manual", "ok": True}
    path.write_text(json.dumps([good, {"started_at": 1}, "文字列"]), encoding="utf-8")
    assert [r.started_at for r in sync_history.get_history()] == ["2026-10-10 10:00:00"]


def test_記録には画面に出す名前を持たない(env):
    src, _ = env
    _write(src / "a.md", "x")
    sync.perform_sync(_config(src))
    raw = sync_history.SYNC_HISTORY_FILE.read_text(encoding="utf-8")
    assert "label" not in raw and "手動" not in raw


def test_記録ファイルの置き場所は設定ファイルの隣():
    from app.config import CONFIG_FILE, SYNC_HISTORY_FILE
    assert SYNC_HISTORY_FILE.parent == CONFIG_FILE.parent and SYNC_HISTORY_FILE != CONFIG_FILE


def test_書き込みの途中で失敗しても前の記録は壊れない(env, monkeypatch):
    src, _ = env
    _write(src / "a.md", "x")
    sync.perform_sync(_config(src))
    before = sync_history.SYNC_HISTORY_FILE.read_text(encoding="utf-8")

    def fail_replace(*args):
        raise OSError("書き込めない")

    monkeypatch.setattr(sync_history.os, "replace", fail_replace)
    sync.perform_sync(_config(src))   # 記録に書けなくても同期そのものは止めない
    assert sync_history.SYNC_HISTORY_FILE.read_text(encoding="utf-8") == before
    assert list(sync_history.SYNC_HISTORY_FILE.parent.glob(".sync_history.*")) == []   # 一時ファイルを残さない


# ---------- 保留した削除を確認して消したとき ----------

def test_確認して削除したら別の1回として残す(env):
    src, content = env
    for i in range(4):
        _write(src / f"n{i}.md", "x")
    sync.perform_sync(_config(src))
    for i in range(3):
        (src / f"n{i}.md").unlink()
    sync.perform_sync(_config(src))
    held_record = _latest()

    assert sync.confirm_pending_deletions() == 3
    history = _history()
    assert history[1] == held_record   # 直近の同期の記録は書き換えない
    record = history[0]
    assert record["trigger"] == "confirm"
    assert record["ok"] and _files(record, "deleted") == ["n0.md", "n1.md", "n2.md"]
    assert record["held"] == []


def test_確認して削除したあとキャッシュの作り直しで失敗しても記録は残る(env, monkeypatch):
    src, _ = env
    for i in range(4):
        _write(src / f"n{i}.md", "x")
    sync.perform_sync(_config(src))
    for i in range(3):
        (src / f"n{i}.md").unlink()
    sync.perform_sync(_config(src))

    def broken():
        raise RuntimeError("作り直せない")

    monkeypatch.setattr(sync, "refresh_global_caches", broken)
    with pytest.raises(RuntimeError):
        sync.confirm_pending_deletions()
    assert _latest()["trigger"] == "confirm" and _files(_latest(), "deleted") == ["n0.md", "n1.md", "n2.md"]


def test_保留が無ければ確認しても記録しない(env):
    assert sync.confirm_pending_deletions() == 0
    assert sync_history.get_history() == []


# ---------- API ----------

def test_同期の記録のAPIは外部から使えない(env):
    assert TestClient(app, base_url=PUBLIC).get("/api/sync/history").status_code == 403


def test_同期の記録のAPIは新しい順に返す(env):
    src, _ = env
    _write(src / "a.md", "x")
    sync.perform_sync(_config(src))
    sync.perform_sync(_config(src), sync_history.SyncTrigger.AUTO)
    res = TestClient(app, base_url=ADMIN).get("/api/sync/history")
    assert res.status_code == 200
    assert [r["trigger"] for r in res.json()["history"]] == ["auto", "manual"]


def test_記録が無ければAPIは空を返す(env):
    res = TestClient(app, base_url=ADMIN).get("/api/sync/history")
    assert res.json() == {"history": [], "limit": sync_history.SYNC_HISTORY_LIMIT,
                          "file_limit": sync_history.SYNC_HISTORY_FILE_LIMIT}
