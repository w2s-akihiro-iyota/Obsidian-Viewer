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


# ---------- 部品: 保護対象の判定・コピーの要否 ----------

@pytest.mark.parametrize("rel_path, expected", [
    ("samples", True),
    ("samples/sample.md", True),
    ("samples/深い/x.png", True),
    ("logo.png", True),
    ("sub/samples/x.md", False),       # 先頭の階層だけを見る
    ("samples2/x.md", False),          # 名前の前方一致ではない
    ("sub/logo.png", False),
    ("ノート.md", False),
])
def test_保護対象は先頭の階層の名前で判定する(rel_path, expected):
    assert sync._is_protected(rel_path, PROTECTED) is expected


def test_コピー先に無ければコピーが要る(tmp_path):
    _write(tmp_path / "src.md", "x", mtime=1_000_000)
    assert sync._needs_copy(tmp_path / "src.md", tmp_path / "無い.md") is True


def test_大きさも更新日時も同じならコピーは要らない(tmp_path):
    _write(tmp_path / "src.md", "abc", mtime=1_000_000)
    _write(tmp_path / "dst.md", "xyz", mtime=1_000_000)
    assert sync._needs_copy(tmp_path / "src.md", tmp_path / "dst.md") is False


def test_大きさが違えば更新日時が同じでもコピーが要る(tmp_path):
    _write(tmp_path / "src.md", "abcd", mtime=1_000_000)
    _write(tmp_path / "dst.md", "abc", mtime=1_000_000)
    assert sync._needs_copy(tmp_path / "src.md", tmp_path / "dst.md") is True


@pytest.mark.parametrize("diff, expected", [
    (0.5, False),
    (1.0, False),      # 1 秒までの差はタイムスタンプの精度の違いとみなす
    (1.5, True),
    (-1.5, True),      # コピー先のほうが新しくても、違えば同期元に合わせる
])
def test_更新日時は1秒を超えて違えばコピーが要る(tmp_path, diff, expected):
    _write(tmp_path / "src.md", "abc", mtime=1_000_000 + diff)
    _write(tmp_path / "dst.md", "abc", mtime=1_000_000)
    assert sync._needs_copy(tmp_path / "src.md", tmp_path / "dst.md") is expected


# ---------- F-11: 追加の同期元 ----------

from app.models.sync import ExtraSource, SyncConfig


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """Vault（notes と llm-wiki）とビューアの content を tmp_path に作り、同期の外部とのつながりを切る"""
    root, content = tmp_path / "vault", tmp_path / "content"
    for d in (root / "notes", root / "llm-wiki", content, tmp_path / "media"):
        d.mkdir(parents=True)
    monkeypatch.setattr(sync, "CONTENT_DIR", content)
    monkeypatch.setattr(sync, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(sync, "_pending", {})
    monkeypatch.setattr(sync, "refresh_global_caches", lambda: None)
    monkeypatch.setattr(sync, "save_config", lambda config: None)
    return root, content


def _cfg(root: Path, *extras: ExtraSource) -> SyncConfig:
    return SyncConfig(sync_enabled=True, content_src=str(root / "notes"), extra_sources=list(extras))


def _wiki(root: Path, **kwargs) -> ExtraSource:
    return ExtraSource(src=str(root / "llm-wiki"), dest="llm-wiki", **kwargs)


def test_追加の同期元は置き場所の下にコピーする(vault):
    root, content = vault
    _write(root / "notes" / "a.md", "A")
    _write(root / "llm-wiki" / "wiki" / "x.md", "X")
    ok, _ = sync.perform_sync(_cfg(root, _wiki(root)))
    assert ok
    assert (content / "a.md").read_text(encoding="utf-8") == "A"
    assert (content / "llm-wiki" / "wiki" / "x.md").read_text(encoding="utf-8") == "X"
    assert not (content / "wiki").exists()


def test_元フォルダの同期は追加の同期元の置き場所を消さない(vault):
    root, content = vault
    _write(root / "notes" / "a.md", "A")
    _write(root / "llm-wiki" / "x.md", "X")
    for _ in range(2):
        sync.perform_sync(_cfg(root, _wiki(root)))
    assert (content / "llm-wiki" / "x.md").exists()


def test_運ばないものはコピーせず_コピー先にあれば消す(vault):
    root, content = vault
    _write(root / "llm-wiki" / "wiki" / "x.md", "X")
    _write(root / "llm-wiki" / "wiki" / "y.md", "Y")
    for i in range(3):
        _write(root / "llm-wiki" / f"z{i}.md", "Z")   # 消す割合を半分未満にして、保留させない
    _write(root / "llm-wiki" / "raw" / "r.md", "R")
    _write(root / "llm-wiki" / ".obsidian" / "app.json", "{}")
    sync.perform_sync(_cfg(root, _wiki(root, exclude=["raw"])))
    assert not (content / "llm-wiki" / "raw").exists()
    assert not (content / "llm-wiki" / ".obsidian").exists()
    # すでにコピー先にあるものは、あとから除外すると消える（同期元には残っていても）
    sync.perform_sync(_cfg(root, _wiki(root, exclude=["raw", "wiki/y.md"])))
    assert (content / "llm-wiki" / "wiki" / "x.md").exists()
    assert not (content / "llm-wiki" / "wiki" / "y.md").exists()
    assert (root / "llm-wiki" / "wiki" / "y.md").exists()


def test_元フォルダのドットで始まるものは運ばない(vault):
    root, content = vault
    _write(root / "notes" / "a.md", "A")
    _write(root / "notes" / ".obsidian" / "app.json", "{}")
    sync.perform_sync(_cfg(root))
    assert (content / "a.md").exists() and not (content / ".obsidian").exists()


def test_sync_directoryの運ばない判定(dirs):
    src, dst = dirs
    _write(src / "a.md", "A")
    _write(src / "skip" / "b.md", "B")
    result = sync.sync_directory(src, dst, [], excluded=lambda rel: rel.startswith("skip/"))
    assert result.added == ["a.md"]
    assert not (dst / "skip").exists()


def test_元フォルダの直下に同じ名前があれば追加の同期元は飛ばして失敗にする(vault):
    root, content = vault
    _write(root / "notes" / "a.md", "A")
    _write(root / "notes" / "llm-wiki" / "n.md", "N")   # ぶつかる
    _write(root / "llm-wiki" / "x.md", "X")
    _write(root / "other" / "o.md", "O")
    _write(content / "llm-wiki" / "old.md", "old")
    other = ExtraSource(src=str(root / "other"), dest="other")
    ok, message = sync.perform_sync(_cfg(root, _wiki(root), other))
    assert not ok and "llm-wiki" in message
    assert (content / "a.md").exists()                       # 元フォルダは同期する
    assert (content / "other" / "o.md").exists()             # ほかの追加の同期元も同期する
    assert not (content / "llm-wiki" / "x.md").exists()      # 飛ばしたものは運ばない
    assert (content / "llm-wiki" / "old.md").exists()        # コピー先の中身も消さない


def test_同期元のフォルダが無い追加の同期元は飛ばして失敗にする(vault):
    root, content = vault
    _write(root / "notes" / "a.md", "A")
    _write(content / "gone" / "old.md", "old")
    ok, message = sync.perform_sync(_cfg(root, ExtraSource(src=str(root / "gone"), dest="gone")))
    assert not ok and "gone" in message
    assert (content / "a.md").exists() and (content / "gone" / "old.md").exists()


def test_設定に誤りのある追加の同期元は飛ばして失敗にする(vault):
    root, content = vault
    _write(root / "notes" / "a.md", "A")
    _write(root / "llm-wiki" / "x.md", "X")
    ok, message = sync.perform_sync(_cfg(root, ExtraSource(src=str(root / "llm-wiki"), dest="a/b")))
    assert not ok and "a/b" in message
    assert (content / "a.md").exists() and not (content / "a").exists()


def test_飛ばしてもlast_syncは更新しキャッシュは作り直す(vault, monkeypatch):
    root, _ = vault
    called = []
    monkeypatch.setattr(sync, "refresh_global_caches", lambda: called.append(1))
    config = _cfg(root, ExtraSource(src=str(root / "gone"), dest="gone"))
    sync.perform_sync(config)
    assert config.last_sync and called == [1]


def test_追加の同期元の保留はビューアのパスで一覧に出て確認で消える(vault):
    root, content = vault
    for i in range(4):
        _write(root / "llm-wiki" / f"w{i}.md", "x")
    sync.perform_sync(_cfg(root, _wiki(root)))
    for i in range(3):
        (root / "llm-wiki" / f"w{i}.md").unlink()
    sync.perform_sync(_cfg(root, _wiki(root)))

    pending = sync.get_pending_deletions()
    assert len(pending) == 1 and pending[0]["label"] == "ノート"
    assert pending[0]["files"] == ["llm-wiki/w0.md", "llm-wiki/w1.md", "llm-wiki/w2.md"]
    assert sync.pending_deletion_count() == 3
    assert sync.confirm_pending_deletions() == 3
    assert sorted(p.name for p in (content / "llm-wiki").iterdir()) == ["w3.md"]
    assert sync.get_pending_deletions() == []


def test_保留は同期元ごとに持つ(vault):
    root, content = vault
    for i in range(4):
        _write(root / "notes" / f"n{i}.md", "x")
        _write(root / "llm-wiki" / f"w{i}.md", "x")
    sync.perform_sync(_cfg(root, _wiki(root)))
    for i in range(3):
        (root / "notes" / f"n{i}.md").unlink()
        (root / "llm-wiki" / f"w{i}.md").unlink()
    sync.perform_sync(_cfg(root, _wiki(root)))
    files = sorted(f for p in sync.get_pending_deletions() for f in p["files"])
    assert files == ["llm-wiki/w0.md", "llm-wiki/w1.md", "llm-wiki/w2.md", "n0.md", "n1.md", "n2.md"]
    assert {"content", "content:llm-wiki"} == set(sync._pending)


def test_設定から外された追加の同期元の保留は消える(vault):
    root, _ = vault
    for i in range(4):
        _write(root / "llm-wiki" / f"w{i}.md", "x")
    _write(root / "notes" / "a.md", "A")
    sync.perform_sync(_cfg(root, _wiki(root)))
    for i in range(3):
        (root / "llm-wiki" / f"w{i}.md").unlink()
    sync.perform_sync(_cfg(root, _wiki(root)))
    assert sync.pending_deletion_count() == 3
    sync.perform_sync(_cfg(root))
    assert "content:llm-wiki" not in sync._pending   # 置き場所の中身は、元フォルダ側の保留（content）に変わる


def test_追加の同期元が無ければ今までどおり(vault):
    root, content = vault
    _write(root / "notes" / "a.md", "A")
    ok, _ = sync.perform_sync(_cfg(root))
    assert ok and (content / "a.md").exists()


def test_srcが空の追加の同期元の置き場所も元フォルダの同期で消えない(vault):
    root, content = vault
    _write(root / "notes" / "a.md", "A")
    _write(content / "llm-wiki" / "old.md", "old")
    ok, _ = sync.perform_sync(_cfg(root, ExtraSource(src="", dest="llm-wiki")))
    assert not ok
    assert (content / "llm-wiki" / "old.md").exists()
