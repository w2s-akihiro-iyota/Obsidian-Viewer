"""既存ノート編集（app/services/note_editing.py）の契約テスト

実行: docker exec -w /app obsidian-viewer-app python -m pytest tests/test_note_editing.py -q
（pytest は requirements-dev.txt）
"""
import hashlib
from pathlib import Path

import pytest

from app import cache
from app.models.sync import SyncConfig
from app.services import note_editing
from app.services.note_editing import NoteConflictError, NoteNotFoundError, VaultWriteError


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """ビューア側（content）と Vault 側（notes）に同じノートを置いた状態を作る"""
    app_dir = tmp_path / "content"
    vault_dir = tmp_path / "vault" / "notes"
    for d in (app_dir / "会議", vault_dir / "会議"):
        d.mkdir(parents=True)
    (app_dir / "会議" / "定例.md").write_text("old", encoding="utf-8")
    (vault_dir / "会議" / "定例.md").write_text("old", encoding="utf-8")
    # ビューア側にしか無いノート（samples など）
    (app_dir / "only_app.md").write_text("app", encoding="utf-8")
    # 索引に載っていないファイル
    (app_dir / "secret.md").write_text("secret", encoding="utf-8")

    monkeypatch.setattr(note_editing, "CONTENT_DIR", app_dir)
    monkeypatch.setattr(note_editing, "load_config", lambda: SyncConfig(content_src=str(vault_dir)))
    monkeypatch.setattr(cache, "GLOBAL_FILE_CACHE", [{"path": "会議/定例.md"}, {"path": "only_app.md"}])
    return app_dir, vault_dir


# ---------- 事前条件：編集できるのは索引にある既存ノートだけ ----------

@pytest.mark.parametrize("path", ["secret.md", "../vault/notes/会議/定例.md", "/etc/passwd", "会議/無い.md", ""])
def test_索引に無いパスは読めない(dirs, path):
    with pytest.raises(NoteNotFoundError):
        note_editing.load_note(path)


@pytest.mark.parametrize("path", ["secret.md", "../vault/notes/会議/定例.md", "/etc/passwd"])
def test_索引に無いパスには書けない(dirs, path):
    app_dir, _ = dirs
    with pytest.raises(NoteNotFoundError):
        note_editing.save_note(path, "x", base_hash=_hash("secret"))
    assert (app_dir / "secret.md").read_text(encoding="utf-8") == "secret"


# ---------- 読み込み：Vault 側を正として読む ----------

def test_Vault側の中身とハッシュを返す(dirs):
    _, vault_dir = dirs
    (vault_dir / "会議" / "定例.md").write_text("vault-latest", encoding="utf-8")
    content, digest = note_editing.load_note("会議/定例.md")
    assert content == "vault-latest"
    assert digest == _hash("vault-latest")


def test_Vaultに無いノートはビューア側を読む(dirs):
    content, digest = note_editing.load_note("only_app.md")
    assert content == "app"
    assert digest == _hash("app")


# ---------- 事後条件：保存すると両方が同じ中身になる ----------

def test_保存すると両方が書き換わる(dirs):
    app_dir, vault_dir = dirs
    result = note_editing.save_note("会議/定例.md", "new", base_hash=_hash("old"))
    assert (vault_dir / "会議" / "定例.md").read_text(encoding="utf-8") == "new"
    assert (app_dir / "会議" / "定例.md").read_text(encoding="utf-8") == "new"
    assert result.hash == _hash("new")
    assert result.host_saved is True


def test_Vaultに無いノートはビューア側だけ書く(dirs):
    app_dir, vault_dir = dirs
    result = note_editing.save_note("only_app.md", "app2", base_hash=_hash("app"))
    assert (app_dir / "only_app.md").read_text(encoding="utf-8") == "app2"
    assert not (vault_dir / "only_app.md").exists()
    assert result.host_saved is False


# ---------- 不変条件：衝突したら何も変えない ----------

def test_開いたあとにVaultが更新されていたら保存しない(dirs):
    app_dir, vault_dir = dirs
    (vault_dir / "会議" / "定例.md").write_text("edited-in-obsidian", encoding="utf-8")
    with pytest.raises(NoteConflictError) as e:
        note_editing.save_note("会議/定例.md", "mine", base_hash=_hash("old"))
    assert e.value.current_hash == _hash("edited-in-obsidian")
    assert (vault_dir / "会議" / "定例.md").read_text(encoding="utf-8") == "edited-in-obsidian"
    assert (app_dir / "会議" / "定例.md").read_text(encoding="utf-8") == "old"


def test_上書き指定なら衝突していても保存する(dirs):
    _, vault_dir = dirs
    (vault_dir / "会議" / "定例.md").write_text("edited-in-obsidian", encoding="utf-8")
    note_editing.save_note("会議/定例.md", "mine", base_hash=_hash("old"), force=True)
    assert (vault_dir / "会議" / "定例.md").read_text(encoding="utf-8") == "mine"


# ---------- 不変条件：Vault に書けなければビューア側も書かない ----------

def test_Vaultへの書き込みに失敗したらビューア側も変えない(dirs, monkeypatch):
    app_dir, vault_dir = dirs
    real_write = note_editing._write_text

    def fail_on_vault(path: Path, content: str) -> None:
        if vault_dir in path.parents:
            raise PermissionError("read-only")
        real_write(path, content)

    monkeypatch.setattr(note_editing, "_write_text", fail_on_vault)
    with pytest.raises(VaultWriteError):
        note_editing.save_note("会議/定例.md", "new", base_hash=_hash("old"))
    assert (app_dir / "会議" / "定例.md").read_text(encoding="utf-8") == "old"


def test_空の中身は保存しない(dirs):
    with pytest.raises(ValueError):
        note_editing.save_note("会議/定例.md", "   \n", base_hash=_hash("old"))


# ---------- 書き込みの途中で失敗しても、元の中身が残る ----------

def test_置き換えの直前で失敗してもVaultの元の中身が残る(dirs, monkeypatch):
    app_dir, vault_dir = dirs

    def fail_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(note_editing.os, "replace", fail_replace)
    with pytest.raises(VaultWriteError):
        note_editing.save_note("会議/定例.md", "new", base_hash=_hash("old"))
    assert (vault_dir / "会議" / "定例.md").read_text(encoding="utf-8") == "old"
    assert (app_dir / "会議" / "定例.md").read_text(encoding="utf-8") == "old"
    # 一時ファイルを残さない
    assert sorted(p.name for p in (vault_dir / "会議").iterdir()) == ["定例.md"]


def test_ビューア側だけ失敗したらVaultは更新済みとして返す(dirs, monkeypatch):
    app_dir, vault_dir = dirs
    real_write = note_editing._write_text

    def fail_on_app(path: Path, content: str) -> None:
        if app_dir in path.parents:
            raise PermissionError("locked")
        real_write(path, content)

    monkeypatch.setattr(note_editing, "_write_text", fail_on_app)
    result = note_editing.save_note("会議/定例.md", "new", base_hash=_hash("old"))
    assert (vault_dir / "会議" / "定例.md").read_text(encoding="utf-8") == "new"
    assert result.host_saved is True
    assert result.app_saved is False


def test_Vaultに無いノートでビューア側に書けなければ失敗にする(dirs, monkeypatch):
    def fail(path: Path, content: str) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(note_editing, "_write_text", fail)
    with pytest.raises(note_editing.NoteWriteError):
        note_editing.save_note("only_app.md", "app2", base_hash=_hash("app"))


# ---------- 改行コードは元のファイルに合わせる ----------

def test_CRLFのノートはCRLFのまま保存する(dirs):
    _, vault_dir = dirs
    target = vault_dir / "会議" / "定例.md"
    target.write_bytes("a\r\nb\r\n".encode("utf-8"))
    _, digest = note_editing.load_note("会議/定例.md")
    # ブラウザの textarea は改行を LF にして送ってくる
    result = note_editing.save_note("会議/定例.md", "a\nb\nc\n", base_hash=digest)
    assert target.read_bytes() == "a\r\nb\r\nc\r\n".encode("utf-8")
    # 返すハッシュは実際に書いた中身のもの（次の保存で衝突と誤判定しない）
    assert note_editing.load_note("会議/定例.md")[1] == result.hash


def test_LFのノートはLFのまま保存する(dirs):
    _, vault_dir = dirs
    note_editing.save_note("会議/定例.md", "x\ny\n", base_hash=_hash("old"))
    assert (vault_dir / "会議" / "定例.md").read_bytes() == b"x\ny\n"
