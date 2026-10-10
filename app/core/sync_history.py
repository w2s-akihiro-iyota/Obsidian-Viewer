"""同期の記録（F-7）: 同期 1 回ごとの結果を JSON ファイルに直近の数回分だけ残す

- 記録は新しい順のリスト。SYNC_HISTORY_LIMIT 件を超えた古いものは捨てる
- ファイル一覧は種類（追加・更新・削除）ごとに SYNC_HISTORY_FILE_LIMIT 件まで。件数は全件を残す
- 書き込みは一時ファイルに書いてから置き換える（途中で止まっても壊れたファイルを残さない）
- 読めない・壊れているときは、記録が無いものとして扱う（形の合わない記録は 1 件ずつ捨てる）
- 同期のスレッドと API のスレッドから触るため、読み書きは _history_lock の中で行う
"""
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import ValidationError

from app.config import SYNC_HISTORY_FILE, SYNC_HISTORY_FILE_LIMIT, SYNC_HISTORY_LIMIT
from app.models.sync import ChangeList, HeldInfo, KindRecord, SyncRecord

logger = logging.getLogger("app.sync")

_history_lock = threading.Lock()


class SyncTrigger:
    """同期のきっかけ（画面に出す名前は settings.js の表で引く）"""
    MANUAL = "manual"     # 設定画面の「今すぐ同期」
    AUTO = "auto"         # 自動同期（バックグラウンド）
    CONFIRM = "confirm"   # 保留していた削除を「確認して削除する」で実行した


@dataclass(frozen=True)
class KindChanges:
    """1 種類（ノート・画像）の変更。記録を作るときの入力"""
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)   # 削除を保留したファイル
    hold_reason: str = ""


def _change_list(files: list[str]) -> ChangeList:
    """件数は全件、ファイルは上限まで"""
    return ChangeList(count=len(files), files=files[:SYNC_HISTORY_FILE_LIMIT])


def build_record(started_at: datetime, duration_sec: float, trigger: str, error: str,
                 changes: dict[str, KindChanges]) -> SyncRecord:
    """
    同期 1 回分の記録を作る

    changes は {種類: 変更}（種類は "content" / "images"）。error が空なら成功とみなす。
    """
    return SyncRecord(
        started_at=started_at.strftime("%Y-%m-%d %H:%M:%S"),
        duration_sec=round(duration_sec, 1),
        trigger=trigger,
        ok=not error,
        error=error,
        kinds={
            kind: KindRecord(added=_change_list(c.added), updated=_change_list(c.updated),
                             deleted=_change_list(c.deleted))
            for kind, c in changes.items()
        },
        held=[HeldInfo(kind=kind, count=len(c.held), reason=c.hold_reason) for kind, c in changes.items() if c.held],
    )


def _read() -> list[SyncRecord]:
    """記録を読む。無い・読めない・リストでないときは空。形の合わない記録は捨てる"""
    try:
        data = json.loads(SYNC_HISTORY_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        logger.warning("Could not read sync history %s: %s", SYNC_HISTORY_FILE, e)
        return []
    if not isinstance(data, list):
        logger.warning("Ignored sync history %s: not a list", SYNC_HISTORY_FILE)
        return []
    records = []
    for item in data:
        try:
            records.append(SyncRecord.model_validate(item))
        except ValidationError as e:
            logger.warning("Ignored a broken sync history record: %s", e)
    return records


def _write(records: list[SyncRecord]) -> None:
    """一時ファイルに書いてから置き換える"""
    SYNC_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=SYNC_HISTORY_FILE.parent, prefix=".sync_history.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in records], f, ensure_ascii=False, indent=1)
        os.replace(tmp, SYNC_HISTORY_FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add_record(record: SyncRecord) -> None:
    """記録を先頭に足し、上限を超えた古いものを捨てる。書けなくても同期そのものは止めない"""
    with _history_lock:
        records = ([record] + _read())[:SYNC_HISTORY_LIMIT]
        try:
            _write(records)
        except OSError as e:
            logger.error("Could not write sync history %s: %s", SYNC_HISTORY_FILE, e)


def get_history() -> list[SyncRecord]:
    """記録を新しい順に返す"""
    with _history_lock:
        return _read()
