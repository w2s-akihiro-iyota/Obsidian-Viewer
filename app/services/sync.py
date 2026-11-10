import shutil
import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable
from app.config import CONTENT_DIR, MEDIA_DIR, PROTECTED_MEDIA_ITEMS, SYNC_DELETE_HOLD_RATIO
from app.models.sync import SyncConfig
from app.core.content_sources import ContentSource, ContentSources
from app.core.indexing import refresh_global_caches
from app.core.sync_history import KindChanges, SyncTrigger, add_record, build_record
from app.events import config_updated_event
# 設定ファイルの読み書き（同期の完了時刻の保存と、自動同期のループで使う）
from app.services.sync_config import load_config, save_config

from app.utils.messages import get_system, get_error, get_warning

logger = logging.getLogger("app.sync")

JST = timezone(timedelta(hours=9))

# 同期（と保留した削除の実行）は同時に 1 本だけ。重なったら SyncInProgressError
_sync_lock = threading.Lock()


class SyncInProgressError(Exception):
    """ほかの同期が実行中"""


class SyncKind:
    """同期の対象。保留した削除の区別と、画面に出す名前に使う"""
    CONTENT = "content"
    IMAGES = "images"
    LABELS = {CONTENT: "ノート", IMAGES: "画像"}


@dataclass
class DirSyncResult:
    added: list[str] = field(default_factory=list)     # コピー先に無かったのでコピーした
    updated: list[str] = field(default_factory=list)   # コピー先にあったが、変わっていたのでコピーし直した
    deleted: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)   # 削除を保留したファイル
    hold_reason: str = ""

    @property
    def copied(self) -> int:
        """コピーした件数（追加＋更新）"""
        return len(self.added) + len(self.updated)

    def to_changes(self) -> KindChanges:
        """同期の記録（F-7）に渡す形にする"""
        return KindChanges(added=self.added, updated=self.updated, deleted=self.deleted,
                           held=self.held, hold_reason=self.hold_reason)


@dataclass
class SyncRun:
    """同期（または保留した削除の実行）1 回分。開始時刻と種類ごとの結果を持ち、終わったら _record で記録する"""
    trigger: str
    started: datetime = field(default_factory=lambda: datetime.now(JST))
    clock: float = field(default_factory=time.monotonic)
    results: dict[str, DirSyncResult] = field(default_factory=dict)

    def add(self, kind: str, result: DirSyncResult) -> DirSyncResult:
        """種類ごとの結果を足す（途中で失敗しても、そこまでの結果を記録に残すため、終わった種類から足す）"""
        self.results[kind] = result
        return result


def _record(run: SyncRun, error: str = "") -> None:
    """1 回分を同期の記録に残す。error が空なら成功"""
    add_record(build_record(run.started, time.monotonic() - run.clock, run.trigger, error,
                            {kind: r.to_changes() for kind, r in run.results.items()}))


@dataclass
class PendingDeletion:
    """確認待ちの削除（設定画面の「ファイル同期」から実行する）"""
    src_dir: Path
    dest_dir: Path
    protected: list[str]
    result: DirSyncResult
    detected_at: str
    excluded: Callable[[str], bool] | None = None   # 運ばないもの（同期のときと同じ判定で消す）
    prefix: str = ""   # 画面に出すときに前に付けるビューアの置き場所（"llm-wiki/" など）


# {キー: PendingDeletion}。キーは元フォルダが SyncKind の値、追加の同期元は "content:" + 置き場所。
# 同期のたびに作り直す（メモリだけに持つ）
# 同期スレッドと API のスレッドから触るため、必ず _pending_lock の中で読み書きする
_pending: dict[str, PendingDeletion] = {}
_pending_lock = threading.Lock()


def _set_pending(kind: str, pending: PendingDeletion | None) -> None:
    with _pending_lock:
        if pending is None:
            _pending.pop(kind, None)
        else:
            _pending[kind] = pending


# ---------- ディレクトリ単位の同期 ----------

def _list_files(root: Path) -> dict[str, Path]:
    """root 配下のファイルを {"相対パス（/区切り）": 実パス} で返す"""
    return {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}


def _is_protected(rel_path: str, protected: list[str]) -> bool:
    return rel_path.split("/", 1)[0] in protected


def _needs_copy(src: Path, dest: Path) -> bool:
    """コピー先が無いか、大きさ・更新日時が違えばコピーする（copy2 は更新日時を引き継ぐ）"""
    if not dest.exists():
        return True
    s, d = src.stat(), dest.stat()
    # ホストとコンテナでタイムスタンプの精度が違うことがあるため、1 秒までの差は同じとみなす
    return s.st_size != d.st_size or abs(s.st_mtime - d.st_mtime) > 1


def _hold_reason(src_count: int, dest_count: int, stale_count: int) -> str:
    """削除を保留すべきならその理由を返す。保留しないなら空文字"""
    if stale_count == 0:
        return ""
    if src_count == 0:
        return get_warning("W004")
    if dest_count and stale_count / dest_count >= SYNC_DELETE_HOLD_RATIO:
        return get_warning("W005").format(ratio=round(SYNC_DELETE_HOLD_RATIO * 100), count=stale_count, total=dest_count)
    return ""


def _delete_files(src_dir: Path, dest_dir: Path, rel_paths: list[str],
                  excluded: Callable[[str], bool] | None = None) -> list[str]:
    """
    ファイルを消し、空になったフォルダも消す。消せたものを返す

    消す直前に同期元をもう一度確かめ、あればそのファイルは消さない
    （同期の途中でエディタから保存された、マウントが戻った、など）。
    ただし運ばないもの（excluded）は、同期元にあっても「無い」ものとして消す。
    """
    deleted = []
    for rel in rel_paths:
        if (src_dir / rel).exists() and not (excluded and excluded(rel)):
            continue
        target = dest_dir / rel
        try:
            target.unlink()
            deleted.append(rel)
        except FileNotFoundError:
            continue
        except OSError as e:
            logger.warning("Could not delete %s: %s", target, e)
            continue
        # 空になった親フォルダを、コピー先の直下まで遡って消す
        parent = target.parent
        while parent != dest_dir and dest_dir in parent.parents:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    return deleted


def sync_directory(src_dir: Path, dest_dir: Path, protected: list[str],
                   excluded: Callable[[str], bool] | None = None) -> DirSyncResult:
    """
    src_dir の内容を dest_dir にそろえ、結果を返す（保留の登録は呼び出し側で行う）

    - 無いファイル・変わったファイルをコピーする（前回の同期時刻には頼らない）
    - src_dir に無いファイルは消す。ただし保護対象は残す
    - 削除の候補は「同期を始める前から dest_dir にあったファイル」だけ。同期中に作られたファイルは消さない
    - excluded に当たるもの（同期元からの相対パスで判定）は運ばない。コピー先にあれば「同期元に無い」ものとして消す
    - 同期元が空、または削除が多すぎる場合は、削除せずに held と hold_reason に入れて返す
    """
    result = DirSyncResult()
    # 先にコピー先を一覧にしておく（このあと作られたファイルを削除の候補に入れないため）
    existing = {rel for rel in _list_files(dest_dir) if not _is_protected(rel, protected)}
    src_files = _list_files(src_dir)
    if excluded:
        src_files = {rel: path for rel, path in src_files.items() if not excluded(rel)}

    for rel, src in src_files.items():
        dest = dest_dir / rel
        try:
            if _needs_copy(src, dest):
                # コピーする前に、コピー先にあったか（＝更新）を見ておく
                existed = dest.exists()
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                (result.updated if existed else result.added).append(rel)
        except FileNotFoundError:
            # 一覧を取ったあとに同期元から消えた（OneDrive の同期中など）。次回の同期で扱う
            logger.info("Skipped (removed during sync): %s", src)

    stale = sorted(existing - src_files.keys())
    reason = _hold_reason(len(src_files), len(existing | src_files.keys()), len(stale))
    if reason:
        result.held, result.hold_reason = stale, reason
        logger.warning("Held %d deletions in %s: %s", len(stale), dest_dir, reason)
    else:
        result.deleted = _delete_files(src_dir, dest_dir, stale, excluded)
        if result.deleted:
            logger.info("Deleted %d files from %s", len(result.deleted), dest_dir)
    return result


def _sync_kind(kind: str, src_dir: Path, dest_dir: Path, protected: list[str],
               excluded: Callable[[str], bool] | None = None, key: str = "", prefix: str = "") -> DirSyncResult:
    """
    1 つの同期元を同期し、保留があれば登録する（無ければ前回の保留を消す）

    key は保留を区別する名前（省略すると kind）。prefix は、保留の画面表示で前に付けるビューアの置き場所。
    """
    result = sync_directory(src_dir, dest_dir, protected, excluded)
    _set_pending(key or kind, PendingDeletion(
        src_dir=src_dir, dest_dir=dest_dir, protected=protected, result=result,
        detected_at=datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
        excluded=excluded, prefix=prefix,
    ) if result.held else None)
    return result


def _absorb(total: DirSyncResult, result: DirSyncResult, prefix: str = "") -> None:
    """同期元 1 つ分の結果を、ノート全体の結果に足す。ファイル名には prefix（ビューアの置き場所）を付ける"""
    total.added += [prefix + f for f in result.added]
    total.updated += [prefix + f for f in result.updated]
    total.deleted += [prefix + f for f in result.deleted]
    total.held += [prefix + f for f in result.held]
    if result.hold_reason and result.hold_reason not in total.hold_reason:
        total.hold_reason = f"{total.hold_reason} / {result.hold_reason}" if total.hold_reason else result.hold_reason


def _pending_key(kind: str, dest: str = "") -> str:
    """保留のキーを作る。元フォルダ・画像は kind のまま、追加の同期元は "content:置き場所" """
    return f"{kind}:{dest}" if dest else kind


def _split_pending_key(key: str) -> tuple[str, str]:
    """保留のキーを (kind, 置き場所) に分ける。置き場所は元フォルダ・画像なら空"""
    kind, _, dest = key.partition(":")
    return kind, dest


def _sync_extras(sources: ContentSources, total: DirSyncResult) -> list[str]:
    """
    追加の同期元を同期して total に足し、飛ばした理由のメッセージを返す

    飛ばすのは、元フォルダの直下に同じ名前がある・同期元のフォルダが無い・設定に誤りがあるもの。
    飛ばしたものはコピー先の中身も消さない。
    """
    skipped = []
    conflicting = {c.dest for c in sources.conflicts()}
    synced_keys = set()
    for extra in sources.extras:
        key = _pending_key(SyncKind.CONTENT, extra.dest)
        if extra.dest in conflicting:
            skipped.append(get_error("E009").format(dest=extra.dest))
        elif not extra.src.is_dir():
            skipped.append(get_error("E008").format(dest=extra.dest))
        else:
            synced_keys.add(key)
            result = _sync_kind(SyncKind.CONTENT, extra.src, CONTENT_DIR / extra.dest, [],
                                excluded=extra.is_excluded, key=key, prefix=f"{extra.dest}/")
            _absorb(total, result, f"{extra.dest}/")
            continue
        _set_pending(key, None)
    for extra, reason in sources.invalid:
        skipped.append(get_error("E010").format(dest=extra.dest, reason=reason))
    # 設定から外された追加の同期元の保留は消す
    with _pending_lock:
        for key in [k for k in _pending if _split_pending_key(k)[1] and k not in synced_keys]:
            del _pending[key]
    return skipped


# ---------- 同期全体 ----------

def perform_sync(config: SyncConfig, trigger: str = SyncTrigger.MANUAL) -> tuple[bool, str]:
    """
    ファイルの同期を実行します。ほかの同期が実行中なら SyncInProgressError

    同期を有効にしていれば、成否にかかわらず結果を同期の記録（F-7）に残す。trigger は SyncTrigger の値。
    """
    if not _sync_lock.acquire(blocking=False):
        raise SyncInProgressError()
    try:
        logger.info("Starting sync. sync_enabled=%s, content_src=%s", config.sync_enabled, config.content_src)
        if not config.sync_enabled:
            return False, get_system("S104")

        run = SyncRun(trigger)
        try:
            success, message = _perform_sync(config, run)
        except Exception as e:
            success, message = False, f"{get_system('S103')}: {str(e)}"
            logger.error(message, exc_info=True)
        _record(run, "" if success else message)
        return success, message
    finally:
        _sync_lock.release()


def _perform_sync(config: SyncConfig, run: SyncRun) -> tuple[bool, str]:
    """同期の本体。終わった種類から run に結果を足す。想定外の例外は呼び出し側で失敗として扱う"""
    if not config.content_src:
        return False, get_error("E001")

    # 1. ノートの同期（元フォルダ → 追加の同期元の順。記録は「ノート」1 つにまとめる）
    sources = ContentSources.from_config(config)
    origin: ContentSource = sources.origin
    if not origin.src.exists():
        return False, get_error("E002")

    notes = run.add(SyncKind.CONTENT, DirSyncResult())
    _absorb(notes, _sync_kind(SyncKind.CONTENT, origin.src, CONTENT_DIR, sources.protected_for(origin),
                              excluded=origin.is_excluded))
    skipped = _sync_extras(sources, notes)

    # 2. 画像（添付）の同期（オプション）。コピー先は MEDIA_DIR（/media で配信。外部には公開ノートが参照するものだけ）
    images = DirSyncResult()
    img_src_path = Path(config.images_src) if config.images_src else None
    if img_src_path and img_src_path.exists() and MEDIA_DIR.exists():
        logger.info(get_system("S105"))
        images = run.add(SyncKind.IMAGES, _sync_kind(SyncKind.IMAGES, img_src_path, MEDIA_DIR,
                                                      PROTECTED_MEDIA_ITEMS))
    else:
        logger.info("Skipping image sync (not configured or path not found)")
        _set_pending(SyncKind.IMAGES, None)

    # 3. 完了処理（記録するのは開始時刻。表示用で、差分の判定には使わない）
    config.last_sync = run.started.strftime("%Y-%m-%d %H:%M:%S")
    logger.info("Sync finished (started at %s)", config.last_sync)
    save_config(config)

    # キャッシュリフレッシュのトリガー
    refresh_global_caches()

    if skipped:
        # ほかの同期元は済んでいる。飛ばしたものだけを失敗として知らせる
        return False, " ".join(skipped)

    msg = get_system("S108").format(notes=notes.copied, images=images.copied,
                                    deleted=len(notes.deleted) + len(images.deleted))
    held = len(notes.held) + len(images.held)
    if held:
        msg += " " + get_system("S109").format(count=held) + get_warning("W003")
    return True, msg


# ---------- 保留した削除 ----------

def get_pending_deletions() -> list[dict]:
    """確認待ちの削除を画面表示用に返す"""
    with _pending_lock:
        items = list(_pending.items())
    # 追加の同期元は "content:置き場所" のキー。kind と label は種類（content）で出し、ファイルはビューアのパスにする
    return [
        {"kind": _split_pending_key(kind)[0], "label": SyncKind.LABELS.get(_split_pending_key(kind)[0], kind),
         "count": len(p.result.held), "files": [p.prefix + f for f in p.result.held],
         "reason": p.result.hold_reason, "detected_at": p.detected_at}
        for kind, p in items
    ]


def pending_deletion_count() -> int:
    with _pending_lock:
        return sum(len(p.result.held) for p in _pending.values())


def confirm_pending_deletions() -> int:
    """
    保留していた削除を実行し、消した件数を返す

    確認までのあいだに同期元へ戻ったファイル（マウントが戻った等）は消さない。
    """
    if not _sync_lock.acquire(blocking=False):
        raise SyncInProgressError()
    try:
        with _pending_lock:
            items = list(_pending.items())
            _pending.clear()
        if not items:
            # 消すものが無い。ファイルは変わっていないので、キャッシュの作り直しも記録もしない
            return 0
        run = SyncRun(SyncTrigger.CONFIRM)
        for kind, p in items:
            targets = [rel for rel in p.result.held if not _is_protected(rel, p.protected)]
            # 追加の同期元の分も、種類ごとの 1 つにまとめる（ファイルはビューアのパス）
            deleted = _delete_files(p.src_dir, p.dest_dir, targets, p.excluded)
            run.results.setdefault(_split_pending_key(kind)[0], DirSyncResult()).deleted += [p.prefix + f for f in deleted]
        total = sum(len(r.deleted) for r in run.results.values())
        logger.info("Confirmed pending deletions: %d files", total)
        # 同期とは別の 1 回として記録する（直近の同期の記録は書き換えない）。
        # キャッシュの作り直しより先に残す（作り直しで例外が出ても、消したことは記録に残る）
        _record(run)
        refresh_global_caches()
        return total
    finally:
        _sync_lock.release()


background_task_running = False

async def background_sync_loop() -> None:
    """バックグラウンド同期ループ。"""
    global background_task_running
    if background_task_running:
        return
    background_task_running = True

    logger.info("Background sync loop started")
    while True:
        try:
            config = load_config()
            if config.sync_enabled and config.auto_sync_enabled:
                logger.info("Auto-sync triggered")
                loop = asyncio.get_event_loop()
                try:
                    await loop.run_in_executor(None, perform_sync, config, SyncTrigger.AUTO)
                except SyncInProgressError:
                    logger.info("Auto-sync skipped: another sync is running")

            wait_time = (config.interval_minutes * 60) if config.auto_sync_enabled else None

            try:
                await asyncio.wait_for(config_updated_event.wait(), timeout=wait_time)
                logger.info("Config updated signal received. Restarting loop.")
            except asyncio.TimeoutError:
                pass
            finally:
                config_updated_event.clear()

        except Exception as e:
            logger.error("Error in background sync loop: %s", e)
            await asyncio.sleep(60)
