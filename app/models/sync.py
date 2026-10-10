from pydantic import BaseModel

class SyncConfig(BaseModel):
    sync_enabled: bool = False
    auto_sync_enabled: bool = False
    content_src: str = ""
    images_src: str = ""
    interval_minutes: int = 60
    base_url: str = ""
    last_sync: str = ""


# ---------- 同期の記録（F-7） ----------

class ChangeList(BaseModel):
    """1 種類・1 変更（追加・更新・削除のどれか）のファイル。count は全件、files は上限まで"""
    count: int = 0
    files: list[str] = []


class KindRecord(BaseModel):
    """1 種類（ノート・画像）の変更"""
    added: ChangeList = ChangeList()
    updated: ChangeList = ChangeList()
    deleted: ChangeList = ChangeList()


class HeldInfo(BaseModel):
    """削除を保留した種類と件数・理由"""
    kind: str
    count: int
    reason: str


class SyncRecord(BaseModel):
    """同期 1 回分の記録。画面に出す名前（きっかけ・種類）は持たず、画面側の表で引く"""
    started_at: str             # 開始時刻（JST, "YYYY-MM-DD HH:MM:SS"）
    duration_sec: float
    trigger: str                # app.core.sync_history.SyncTrigger の値
    ok: bool
    error: str = ""
    kinds: dict[str, KindRecord] = {}   # {"content" / "images": 変更}
    held: list[HeldInfo] = []
