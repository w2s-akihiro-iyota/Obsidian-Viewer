"""ファイル同期（app/services/sync.py）の契約テスト

B-2: Vault で消したファイルを消す（保護対象は残す・空や大量削除は保留して確認後に実行）
B-3: 前回の同期時刻ではなく、コピー先と比べてコピーする
B-4: 同期は同時に 1 本だけ
"""
import os
import time
from pathlib import Path

import pytest

from app.config import MEDIA_SAMPLES_DIR_NAME, PROTECTED_MEDIA_ITEMS
from app.services import sync


def _write(path: Path, text: str, mtime: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    monkeypatch.setattr(sync, "_pending", {})
    monkeypatch.setattr(sync, "refresh_global_caches", lambda: None)
    return src, dst


PROTECTED = ["samples", "logo.png"]


def _seed(src: Path, dst: Path, n: int = 4) -> None:
    for i in range(n):
        _write(src / f"n{i}.md", "x")
    sync.sync_directory(src, dst, PROTECTED)


# ---------- B-3: コピー先と比べてコピーする ----------

def test_新しいファイルはコピーする(dirs):
    src, dst = dirs
    _write(src / "a.md", "A")
    _write(src / "会議" / "b.md", "B")
    result = sync.sync_directory(src, dst, PROTECTED)
    assert (dst / "a.md").read_text(encoding="utf-8") == "A"
    assert (dst / "会議" / "b.md").read_text(encoding="utf-8") == "B"
    assert result.copied == 2


def test_更新日時が古くてもコピー先に無ければコピーする(dirs):
    src, dst = dirs
    _write(src / "old.md", "restored", mtime=time.time() - 365 * 86400)
    sync.sync_directory(src, dst, PROTECTED)
    assert (dst / "old.md").exists()


def test_中身が変わったファイルはコピーし直す(dirs):
    src, dst = dirs
    _write(src / "a.md", "v1")
    sync.sync_directory(src, dst, PROTECTED)
    _write(src / "a.md", "version2", mtime=time.time() + 10)
    result = sync.sync_directory(src, dst, PROTECTED)
    assert (dst / "a.md").read_text(encoding="utf-8") == "version2"
    assert result.copied == 1


def test_変わっていないファイルはコピーしない(dirs):
    src, dst = dirs
    _write(src / "a.md", "A")
    sync.sync_directory(src, dst, PROTECTED)
    assert sync.sync_directory(src, dst, PROTECTED).copied == 0


def test_同期の途中で同期元から消えたファイルは飛ばして続ける(dirs, monkeypatch):
    src, dst = dirs
    _write(src / "a.md", "A")
    _write(src / "b.md", "B")
    real_copy = sync.shutil.copy2

    def vanish_a(s, d):
        if Path(s).name == "a.md":
            raise FileNotFoundError(s)
        return real_copy(s, d)

    monkeypatch.setattr(sync.shutil, "copy2", vanish_a)
    result = sync.sync_directory(src, dst, PROTECTED)
    assert (dst / "b.md").exists()
    assert result.copied == 1


# ---------- B-2: Vault で消したファイルを消す ----------

def test_同期元に無いファイルは消す(dirs):
    src, dst = dirs
    _seed(src, dst)
    (src / "n0.md").unlink()
    result = sync.sync_directory(src, dst, PROTECTED)
    assert not (dst / "n0.md").exists()
    assert result.deleted == ["n0.md"] and result.held == []


def test_名前を変えたら古いほうは消えて新しいほうが入る(dirs):
    src, dst = dirs
    _seed(src, dst)
    (src / "n0.md").rename(src / "renamed.md")
    sync.sync_directory(src, dst, PROTECTED)
    assert not (dst / "n0.md").exists()
    assert (dst / "renamed.md").exists()


@pytest.mark.parametrize("protected_path", ["samples/sample.md", "logo.png"])
def test_保護対象は消さない(dirs, protected_path):
    src, dst = dirs
    _write(dst / protected_path, "keep")
    _seed(src, dst)
    assert (dst / protected_path).exists()


def test_添付の保護対象は同梱サンプルだけ():
    # 添付の同期先（MEDIA_DIR）にはアプリの部品（logo.png）を置かないので、保護するのは同梱サンプルの置き場だけ
    # （Vault 側の samples/ などは同期元に合わせて消す）
    assert PROTECTED_MEDIA_ITEMS == [MEDIA_SAMPLES_DIR_NAME] and MEDIA_SAMPLES_DIR_NAME != "samples"


def test_空になったフォルダも消す(dirs):
    src, dst = dirs
    _write(src / "古いフォルダ" / "z.md", "x")
    _seed(src, dst)
    (src / "古いフォルダ" / "z.md").unlink()
    (src / "古いフォルダ").rmdir()
    sync.sync_directory(src, dst, PROTECTED)
    assert not (dst / "古いフォルダ").exists()


def test_同期中に作られたファイルは消さない(dirs, monkeypatch):
    """エディタから保存した直後など、同期を始めた後にコピー先へできたファイル"""
    src, dst = dirs
    _seed(src, dst)
    real_copy = sync.shutil.copy2

    def copy_and_editor_saves(s, d):
        (dst / "保存したばかり.md").write_text("new", encoding="utf-8")
        return real_copy(s, d)

    _write(src / "更新.md", "u")
    monkeypatch.setattr(sync.shutil, "copy2", copy_and_editor_saves)
    sync.sync_directory(src, dst, PROTECTED)
    assert (dst / "保存したばかり.md").exists()


def test_消す直前に同期元へ現れたファイルは消さない(dirs):
    src, dst = dirs
    _seed(src, dst)
    deleted = sync._delete_files(src, dst, ["n0.md"])
    assert deleted == [] and (dst / "n0.md").exists()


# ---------- B-2: 空・大量削除は保留する ----------

def test_同期元が空なら削除を保留する(dirs):
    src, dst = dirs
    _write(dst / "a.md", "x")
    result = sync.sync_directory(src, dst, PROTECTED)
    assert (dst / "a.md").exists()
    assert result.held == ["a.md"] and result.hold_reason


def test_ちょうど半分が消える場合は保留する(dirs):
    src, dst = dirs
    _seed(src, dst)
    for i in range(2):
        (src / f"n{i}.md").unlink()
    result = sync.sync_directory(src, dst, PROTECTED)
    assert result.held == ["n0.md", "n1.md"] and result.deleted == []
    assert (dst / "n0.md").exists()


def test_半分未満なら保留しない(dirs):
    src, dst = dirs
    _seed(src, dst, n=5)
    for i in range(2):
        (src / f"n{i}.md").unlink()
    result = sync.sync_directory(src, dst, PROTECTED)
    assert result.held == [] and len(result.deleted) == 2


def test_削除が無ければ理由も無い():
    assert sync._hold_reason(src_count=0, dest_count=0, stale_count=0) == ""


def test_保留中もコピーは行う(dirs):
    src, dst = dirs
    for i in range(4):
        _write(dst / f"old{i}.md", "x")
    _write(src / "new.md", "N")
    result = sync.sync_directory(src, dst, PROTECTED)
    assert (dst / "new.md").exists()
    assert len(result.held) == 4


def test_同期の関数は保留を登録しない(dirs):
    src, dst = dirs
    _write(dst / "a.md", "x")
    sync.sync_directory(src, dst, PROTECTED)
    assert sync.get_pending_deletions() == []


# ---------- B-2: 保留した削除を確認して実行する ----------

def _hold(dirs):
    src, dst = dirs
    _seed(src, dst)
    for i in range(3):
        (src / f"n{i}.md").unlink()
    sync._sync_kind(sync.SyncKind.CONTENT, src, dst, PROTECTED)
    return src, dst


def test_保留の一覧と件数(dirs):
    _hold(dirs)
    pending = sync.get_pending_deletions()
    assert pending[0]["kind"] == "content" and pending[0]["label"] == "ノート"
    assert pending[0]["count"] == 3 and pending[0]["files"] == ["n0.md", "n1.md", "n2.md"]
    assert pending[0]["reason"] and pending[0]["detected_at"]
    assert sync.pending_deletion_count() == 3


def test_次の同期で保留が解消されたら一覧から消える(dirs):
    src, dst = _hold(dirs)
    for i in range(3):
        _write(src / f"n{i}.md", "x")
    sync._sync_kind(sync.SyncKind.CONTENT, src, dst, PROTECTED)
    assert sync.pending_deletion_count() == 0


def test_確認すると保留していたファイルを消す(dirs):
    src, dst = _hold(dirs)
    assert sync.confirm_pending_deletions() == 3
    assert sorted(p.name for p in dst.iterdir()) == ["n3.md"]
    assert sync.get_pending_deletions() == []


def test_確認までに同期元へ戻ったファイルは消さない(dirs):
    src, dst = _hold(dirs)
    _write(src / "n0.md", "back")  # マウントが戻った等で、同期元に再び現れた
    assert sync.confirm_pending_deletions() == 2
    assert (dst / "n0.md").exists()


# ---------- B-4: 同期は同時に 1 本だけ ----------

def test_同期中に同期を始めようとすると断る():
    assert sync._sync_lock.acquire(blocking=False)
    try:
        with pytest.raises(sync.SyncInProgressError):
            sync.perform_sync(sync.SyncConfig(sync_enabled=True, content_src="/nowhere"))
        with pytest.raises(sync.SyncInProgressError):
            sync.confirm_pending_deletions()
    finally:
        sync._sync_lock.release()
