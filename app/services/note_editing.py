"""既存ノートの編集（読み込み・衝突検知つきの保存）

正とするのは Vault 側のファイル（同期元 content_src 配下）。
ビューア側（CONTENT_DIR）は同期で上書きされるコピーなので、Vault と同じ内容を書いてそろえる。
Vault に同じノートが無い場合（samples など）は、ビューア側だけを読み書きする。
"""
import hashlib
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from app import cache
from app.config import CONTENT_DIR
from app.services.sync import load_config

logger = logging.getLogger("app.note_editing")


class NoteNotFoundError(Exception):
    """編集対象として索引に載っていないパスが指定された"""


class NoteConflictError(Exception):
    """開いたあとに、保存先のノートがほかの場所（Obsidian 等）で更新された"""

    def __init__(self, current_hash: str):
        super().__init__("note was updated after it was opened")
        self.current_hash = current_hash


class VaultWriteError(Exception):
    """Vault 側への書き込みに失敗した（このときビューア側も書き換えない）"""


class NoteWriteError(Exception):
    """Vault に無いノートで、ビューア側への書き込みに失敗した"""


@dataclass(frozen=True)
class SaveResult:
    hash: str
    host_saved: bool       # Vault 側を書き換えたか（Vault に無いノートなら False）
    app_saved: bool = True  # ビューア側を書き換えたか。False でも Vault が正なので次の同期でそろう


def content_hash(content: str) -> str:
    """衝突検知に使う中身のハッシュ"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _resolve_inside(base: Path, rel_path: str) -> Path:
    """base 配下のパスに解決する。外に出るパスは NoteNotFoundError"""
    resolved = (base / rel_path).resolve()
    if base.resolve() not in resolved.parents:
        raise NoteNotFoundError(rel_path)
    return resolved


def _note_paths(rel_path: str) -> tuple[Path, Path | None]:
    """(ビューア側のパス, Vault 側のパス or None) を返す。索引に無いノートは扱わない"""
    if not rel_path or not any(f["path"] == rel_path for f in cache.GLOBAL_FILE_CACHE):
        raise NoteNotFoundError(rel_path)

    app_path = _resolve_inside(CONTENT_DIR, rel_path)

    vault_path = None
    content_src = load_config().content_src
    if content_src and Path(content_src).is_dir():
        candidate = _resolve_inside(Path(content_src), rel_path)
        if candidate.is_file():
            vault_path = candidate

    if vault_path is None and not app_path.is_file():
        raise NoteNotFoundError(rel_path)
    return app_path, vault_path


def _read_text(path: Path) -> str:
    # newline="" で改行コードを変えずに読む（ハッシュを Vault の実ファイルと一致させるため）
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _write_text(path: Path, content: str) -> None:
    """
    途中で失敗しても元のファイルが壊れないように書く

    同じフォルダの一時ファイルへ書き切ってから、os.replace で一度に差し替える。
    いきなり open(path, "w") すると、開いた時点で中身が消え、失敗すると空や半端なまま残る。
    """
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _match_line_endings(content: str, original: str) -> str:
    """ブラウザは改行を LF にして送ってくるため、元のファイルが CRLF なら CRLF に戻す"""
    if "\r\n" in original:
        return content.replace("\r\n", "\n").replace("\n", "\r\n")
    return content


def load_note(rel_path: str) -> tuple[str, str]:
    """編集用にノートを読み込み、(中身, ハッシュ) を返す"""
    app_path, vault_path = _note_paths(rel_path)
    content = _read_text(vault_path or app_path)
    return content, content_hash(content)


def save_note(rel_path: str, content: str, base_hash: str, force: bool = False) -> SaveResult:
    """
    ノートを保存する

    base_hash は読み込んだ時点のハッシュ。保存先の今のハッシュと違えば、force でない限り
    何も書かずに NoteConflictError を送出する。
    Vault → ビューアの順に書き、Vault に失敗したらビューア側は書かない。
    """
    if not content.strip():
        raise ValueError("content is empty")

    app_path, vault_path = _note_paths(rel_path)

    current = _read_text(vault_path or app_path)
    current_hash = content_hash(current)
    if current_hash != base_hash and not force:
        raise NoteConflictError(current_hash)

    content = _match_line_endings(content, current)

    if vault_path is None:
        try:
            _write_text(app_path, content)
        except OSError as e:
            raise NoteWriteError(str(e)) from e
        return SaveResult(hash=content_hash(content), host_saved=False)

    try:
        _write_text(vault_path, content)
    except OSError as e:
        raise VaultWriteError(str(e)) from e

    # Vault が正。ビューア側に書けなくても保存は成功として扱い、次の同期でそろえる
    app_saved = True
    try:
        _write_text(app_path, content)
    except OSError as e:
        logger.warning("ビューア側への書き込みに失敗（Vault は更新済み）: %s", e)
        app_saved = False

    # 返すハッシュは実際に書いた中身のもの。次の保存の base_hash になる
    return SaveResult(hash=content_hash(content), host_saved=True, app_saved=app_saved)
