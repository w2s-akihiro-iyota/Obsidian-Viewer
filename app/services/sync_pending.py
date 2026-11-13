"""
同期で保留した削除（確認待ち）の置き場

同期（app/services/sync.py）が同期元ごとに登録・解消する。設定画面の「ファイル同期」はここから一覧と件数を読み、
確認したら sync.py の confirm_pending_deletions がここから取り出して消す。
同期スレッドと API のスレッドから触るため、中身は必ず _lock の中で読み書きする。メモリだけに持つ（再起動で消える）。
"""
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class SyncKind:
    """同期の対象。保留した削除の区別と、画面に出す名前に使う"""
    CONTENT = "content"
    IMAGES = "images"
    LABELS = {CONTENT: "ノート", IMAGES: "画像"}


@dataclass
class PendingDeletion:
    """確認待ちの削除（同期元 1 つ分。設定画面の「ファイル同期」から実行する）"""
    src_dir: Path
    dest_dir: Path
    protected: list[str]
    held: list[str]      # 削除を保留したファイル（コピー先からの相対パス）
    reason: str          # 保留した理由（画面に出す）
    detected_at: str
    excluded: Callable[[str], bool] | None = None   # 運ばないもの（同期のときと同じ判定で消す）
    prefix: str = ""   # 画面に出すときに前に付けるビューアの置き場所（"llm-wiki/" など）


# {キー: PendingDeletion}。キーは pending_key で作る。同期のたびに作り直す
_pending: dict[str, PendingDeletion] = {}
_lock = threading.Lock()


def pending_key(kind: str, dest: str = "") -> str:
    """保留のキーを作る。元フォルダ・画像は kind（SyncKind の値）のまま、追加の同期元は "content:置き場所" """
    return f"{kind}:{dest}" if dest else kind


def split_pending_key(key: str) -> tuple[str, str]:
    """保留のキーを (kind, 置き場所) に分ける。置き場所は元フォルダ・画像なら空"""
    kind, _, dest = key.partition(":")
    return kind, dest


def set_pending(key: str, pending: PendingDeletion | None) -> None:
    """同期元 1 つ分の保留を登録する。None なら消す（保留が解消された）"""
    with _lock:
        if pending is None:
            _pending.pop(key, None)
        else:
            _pending[key] = pending


def drop_extra_pendings(keep: set[str]) -> None:
    """追加の同期元の保留のうち、keep に無いもの（設定から外された・今回は飛ばした）を消す"""
    with _lock:
        for key in [k for k in _pending if split_pending_key(k)[1] and k not in keep]:
            del _pending[key]


def take_all() -> list[tuple[str, PendingDeletion]]:
    """保留を全部取り出して空にする（確認して消すとき）"""
    with _lock:
        items = list(_pending.items())
        _pending.clear()
    return items


def get_pending_deletions() -> list[dict]:
    """確認待ちの削除を画面表示用に返す"""
    with _lock:
        items = list(_pending.items())
    # 追加の同期元は "content:置き場所" のキー。kind と label は種類（content）で出し、ファイルはビューアのパスにする
    return [
        {"kind": kind, "label": SyncKind.LABELS.get(kind, kind),
         "count": len(p.held), "files": [p.prefix + f for f in p.held],
         "reason": p.reason, "detected_at": p.detected_at}
        for kind, p in ((split_pending_key(key)[0], p) for key, p in items)
    ]


def pending_deletion_count() -> int:
    with _lock:
        return sum(len(p.held) for p in _pending.values())
