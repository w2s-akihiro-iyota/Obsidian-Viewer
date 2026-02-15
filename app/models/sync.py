from pydantic import BaseModel

class SyncConfig(BaseModel):
    sync_enabled: bool = False
    auto_sync_enabled: bool = False
    content_src: str = ""
    images_src: str = ""
    interval_minutes: int = 60
    base_url: str = ""
    last_sync: str = ""
