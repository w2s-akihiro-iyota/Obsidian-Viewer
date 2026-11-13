import asyncio
import contextlib
import logging

from app.logging_config import setup_logging
setup_logging()

logger = logging.getLogger("app.main")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.config import STATICS_DIR
from app.api.errors import handle_http_exception, handle_unexpected_error
from app.api.routes import router
from app.core.indexing import refresh_global_caches
from app.services.media_migration import migrate_legacy_media
from app.services.sync import background_sync_loop
from app.utils.helpers import is_same_origin_request
from app.utils.messages import get_error

def _prepare_caches() -> None:
    """起動時の準備。添付を以前の置き場（static/images）から MEDIA_DIR へ移してから、索引を作る"""
    try:
        migrate_legacy_media()
    except Exception:
        # 引っ越しに失敗しても、索引は作って起動を続ける（残ったものは次の起動でまた移す）
        logger.exception("Failed to move attachments to the media directory")
    refresh_global_caches()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """起動と終了の処理（Q-7。前は非推奨の @app.on_event("startup")）

    索引は別スレッドで作り、起動を待たせない。同期ループは裏で回し、終わるときに止める。
    app/server.py は 2 つのサーバーのうち片方だけで lifespan を動かすので、ここは 1 回だけ走る
    """
    logger.info("Obsidian Viewer starting up")
    asyncio.get_running_loop().run_in_executor(None, _prepare_caches)
    # 参照を持っておく（持たないとタスクが途中で消されることがある）
    sync_task = asyncio.create_task(background_sync_loop())
    yield
    sync_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sync_task


app = FastAPI(title="Obsidian Viewer", lifespan=lifespan)

# ブラウザで開いたページのエラーは、JSON ではなくエラー画面で返す（F-10）。
# starlette 側の HTTPException に登録する（FastAPI 側だけだと、存在しない URL の 404 を拾えない）
app.add_exception_handler(StarletteHTTPException, handle_http_exception)
app.add_exception_handler(Exception, handle_unexpected_error)

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
