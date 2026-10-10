import asyncio
import logging

from app.logging_config import setup_logging
setup_logging()

logger = logging.getLogger("app.main")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.config import STATICS_DIR
from app.api.routes import router
from app.core.indexing import refresh_global_caches
from app.services.media_migration import migrate_legacy_media
from app.services.sync import background_sync_loop
from app.utils.helpers import is_same_origin_request
from app.utils.messages import get_error

app = FastAPI(title="Obsidian Viewer")

# 状態を変えるメソッド（CSRF対策の対象）
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def reject_cross_site_writes(request: Request, call_next):
    """別サイトのページから送られた書き込みリクエストを拒否する"""
    if request.method in _UNSAFE_METHODS and not is_same_origin_request(request):
        logger.warning("Cross-site request rejected: %s %s", request.method, request.url.path)
        return JSONResponse({"status": "error", "message": get_error("E102")}, status_code=403)
    return await call_next(request)


# Mount Static Files（アプリの CSS・JS・部品の画像だけ。Vault の添付は /media で配信する: app/api/media.py）
app.mount("/static", StaticFiles(directory=str(STATICS_DIR)), name="static")

# Include API Router
app.include_router(router)


def _prepare_caches() -> None:
    """起動時の準備。添付を以前の置き場（static/images）から MEDIA_DIR へ移してから、索引を作る"""
    try:
        migrate_legacy_media()
    except Exception:
        # 引っ越しに失敗しても、索引は作って起動を続ける（残ったものは次の起動でまた移す）
        logger.exception("Failed to move attachments to the media directory")
    refresh_global_caches()


@app.on_event("startup")
async def startup_event():
    logger.info("Obsidian Viewer starting up")
    # Initialize cache in a thread to avoid blocking startup
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _prepare_caches)
    # Start background sync
    asyncio.create_task(background_sync_loop())
