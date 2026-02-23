"""同期・管理系エンドポイント（localhost限定）"""
# Standard library
import os
from pathlib import Path

# Third party
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# Local
from app.core.indexing import refresh_global_caches
from app.events import config_updated_event
from app.models.sync import SyncConfig
from app.services.sync import load_config, save_config, perform_sync
from app.utils.helpers import localhost_guard
from app.utils.messages import get_error, get_warning

router = APIRouter()


@router.post("/api/sync/save")
async def api_save_sync_settings(request: Request):
    if error := localhost_guard(request): return error

    data = await request.json()

    errors = {}
    warnings = {}

    sync_enabled = data.get('sync_enabled', False)

    # 同期が有効な場合のみパスのバリデーションを実行
    if sync_enabled:
        # 1. Validation (Errors)
        content_src = data.get('content_src', '')
        if not content_src:
            errors['content-src'] = get_error("E001")
        else:
            p = Path(content_src)
            if not p.exists() or not p.is_dir():
                errors['content-src'] = get_error("E002")

        images_src = data.get('images_src', '')
        if images_src:
            p = Path(images_src)
            if not p.exists() or not p.is_dir():
                errors['images-src'] = get_error("E002")

        # 2. Warnings (Non-blocking)
        images_src_trimmed = images_src.strip()
        if not images_src_trimmed:
            warnings['images-src'] = get_warning("W001")

        base_url = data.get('base_url', '').strip()
        if not base_url:
            warnings['base-url'] = get_warning("W002")

    if errors:
        return JSONResponse({
            "status": "error",
            "errors": errors
        }, status_code=400)

    config = SyncConfig(**data)
    save_config(config)
    # 通知を送ってバックグラウンドタスクを起こす
    config_updated_event.set()

    return {
        "status": "success",
        "warnings": warnings
    }


@router.get("/api/sync/config")
async def api_get_sync_config(request: Request):
    if error := localhost_guard(request): return error
    config = load_config()
    return config


@router.get("/api/config")
async def api_get_public_config():
    # Publicly accessible safe config subset
    config = load_config()
    return {
        "base_url": config.base_url,
        "sync_enabled": config.sync_enabled
    }


@router.post("/api/sync/now")
@router.post("/api/sync")
async def api_sync_now(request: Request):
    if error := localhost_guard(request): return error
    config = load_config()
    success, message = perform_sync(config)
    # 同期後、定期実行のタイマーをリセットさせるために通知を送る
    config_updated_event.set()
    if success:
        return {"status": "success", "last_sync": config.last_sync, "message": message}
    else:
        return JSONResponse({"status": "error", "message": message}, status_code=500)


@router.post("/api/reindex")
@router.post("/api/rebuild-index")
async def api_reindex(request: Request):
    if error := localhost_guard(request): return error

    refresh_global_caches()
    return {"status": "success"}


@router.get("/api/dirs")
@router.get("/api/list-dirs")
async def list_dirs(request: Request, path: str = ""):
    if error := localhost_guard(request): return error

    try:
        if not path:
            if os.name == 'nt':  # Windows
                import ctypes
                drives = []
                bitmask = ctypes.windll.kernel32.GetLogicalDrives()
                for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                    if bitmask & 1:
                        drive = f"{letter}:\\"
                        drives.append({"name": drive, "path": drive})
                    bitmask >>= 1
                return {"current": "", "dirs": drives, "is_root": True}
            else:
                path = "/"

        p = Path(path)
        if not p.exists():
            return {"current": path, "dirs": [], "parent": str(p.parent)}

        dirs = [
            {"name": d.name, "path": str(d.absolute())}
            for d in p.iterdir() if d.is_dir() and not d.name.startswith('.')
        ]
        dirs.sort(key=lambda x: x['name'].lower())
        return {
            "current": str(p),
            "dirs": dirs,
            "parent": str(p.parent) if p.parent != p else None
        }
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
