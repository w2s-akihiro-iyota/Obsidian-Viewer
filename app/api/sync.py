"""同期・管理系エンドポイント（localhost限定）"""
# Standard library
import os
from pathlib import Path

# Third party
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

# Local
from app.config import SYNC_HISTORY_FILE_LIMIT, SYNC_HISTORY_LIMIT
from app.core.indexing import refresh_global_caches
from app.core.sync_history import get_history
from app.events import config_updated_event
from app.core.content_sources import extra_source_problems, normalize_exclude
from app.models.sync import ExtraSource, SyncConfig
from app.services.sync import SyncInProgressError, confirm_pending_deletions, perform_sync
from app.services.sync_config import load_config, save_config
from app.services.sync_pending import get_pending_deletions, pending_deletion_count
from app.utils.helpers import admin_guard
from app.utils.messages import get_error, get_system, get_warning

router = APIRouter()


def _validate_extra_sources(extra_sources: list[dict], content_src: str, errors: dict) -> None:
    """追加の同期元の問題を errors に写す（規則は content_sources。キーは extra-src-{行} / extra-dest-{行}）"""
    rows = [ExtraSource(src=str(e.get('src') or ''), dest=str(e.get('dest') or '')) for e in extra_sources]
    for i, field, message in extra_source_problems(rows, content_src, check_filesystem=True):
        errors.setdefault(f'extra-{field}-{i}', message)


@router.post("/api/sync/save")
async def api_save_sync_settings(request: Request):
    if error := admin_guard(request): return error

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

    # 追加の同期元（exclude は空要素・重複を除いて保存する）
    extra_sources = [e for e in (data.get('extra_sources') or []) if isinstance(e, dict)]
    for extra in extra_sources:
        extra['exclude'] = list(normalize_exclude(extra.get('exclude') or []))
    data['extra_sources'] = extra_sources
    if sync_enabled:
        _validate_extra_sources(extra_sources, data.get('content_src', ''), errors)

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
    if error := admin_guard(request): return error
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
    if error := admin_guard(request): return error
    config = load_config()
    # 同期は重いので別スレッドで行い、ほかのリクエストを止めない
    try:
        success, message = await run_in_threadpool(perform_sync, config)
    except SyncInProgressError:
        return JSONResponse({"status": "busy", "message": get_system("S106")}, status_code=409)
    # 同期後、定期実行のタイマーをリセットさせるために通知を送る
    config_updated_event.set()
    if success:
        return {"status": "success", "last_sync": config.last_sync, "message": message,
                "pending_deletions": pending_deletion_count()}
    else:
        return JSONResponse({"status": "error", "message": message}, status_code=500)


@router.get("/api/sync/pending-deletions")
async def api_pending_deletions(request: Request):
    """削除が多すぎる等の理由で保留した削除の一覧（localhost限定）"""
    if error := admin_guard(request): return error
    return {"pending": get_pending_deletions()}


@router.get("/api/sync/history")
async def api_sync_history(request: Request):
    """同期の記録（F-7）。新しい順に直近の数回分と、残す回数・ファイル名の上限（localhost限定）"""
    if error := admin_guard(request): return error
    history = await run_in_threadpool(get_history)
    return {"history": [r.model_dump() for r in history],
            "limit": SYNC_HISTORY_LIMIT, "file_limit": SYNC_HISTORY_FILE_LIMIT}


@router.post("/api/sync/confirm-deletions")
async def api_confirm_deletions(request: Request):
    """保留した削除を、確認のうえで実行する（localhost限定）"""
    if error := admin_guard(request): return error
    try:
        deleted = await run_in_threadpool(confirm_pending_deletions)
    except SyncInProgressError:
        return JSONResponse({"status": "busy", "message": get_system("S106")}, status_code=409)
    return {"status": "success", "message": get_system("S107").format(count=deleted), "deleted": deleted}


@router.post("/api/reindex")
@router.post("/api/rebuild-index")
async def api_reindex(request: Request):
    if error := admin_guard(request): return error

    await run_in_threadpool(refresh_global_caches)
    return {"status": "success"}


@router.get("/api/dirs")
@router.get("/api/list-dirs")
async def list_dirs(request: Request, path: str = ""):
    if error := admin_guard(request): return error

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
