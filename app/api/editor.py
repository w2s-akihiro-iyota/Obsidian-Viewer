"""エディタ系エンドポイント（localhost限定）"""
# Standard library
import logging
from pathlib import Path

# Third party
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

# Local
from app.api import templates

logger = logging.getLogger("app.editor")
from app import cache
from app.config import CONTENT_DIR
from app.core.indexing import refresh_global_caches
from app.services.content import render_markdown
from app.services.sync import load_config
from app.utils.helpers import is_request_local, localhost_guard
from app.utils.messages import get_error, get_system

router = APIRouter()


@router.get("/editor", response_class=HTMLResponse)
async def editor_page(request: Request):
    """エディタページを表示する（localhost限定）"""
    if not is_request_local(request):
        raise HTTPException(status_code=403, detail=get_error("E101"))

    return templates.TemplateResponse("editor.html", {
        "request": request,
        "is_localhost": True
    })


@router.post("/api/editor/preview")
async def editor_preview(request: Request):
    """Markdownプレビューを返す（localhost限定）"""
    if error := localhost_guard(request): return error

    data = await request.json()
    content = data.get("content", "")

    if not content.strip():
        return HTMLResponse(content="<p style='color:var(--text-muted);'>プレビューするコンテンツがありません</p>")

    try:
        html = render_markdown(content)
    except Exception as e:
        logger.error("Preview render error: %s", e)
        html = f"<p style='color:#ff6b6b;'>レンダリングエラー: {e}</p>"

    return HTMLResponse(content=html)


@router.post("/api/editor/save")
async def editor_save(request: Request):
    """Markdownファイルを保存する（localhost限定）"""
    if error := localhost_guard(request): return error

    data = await request.json()
    filename = data.get("filename", "").strip()
    content = data.get("content", "")

    # バリデーション: ファイル名必須
    if not filename:
        return JSONResponse({"status": "error", "message": get_error("E201")}, status_code=400)

    # バリデーション: パストラバーサル防止・無効文字チェック
    if ".." in filename or "/" in filename or "\\" in filename:
        return JSONResponse({"status": "error", "message": get_error("E202")}, status_code=400)

    # Windows無効文字チェック
    invalid_chars = '<>:"|?*'
    if any(c in filename for c in invalid_chars):
        return JSONResponse({"status": "error", "message": get_error("E202")}, status_code=400)

    # .md 拡張子の自動付与
    if not filename.endswith(".md"):
        filename += ".md"

    # コンテンツ空チェック
    if not content.strip():
        return JSONResponse({"status": "error", "message": get_error("E203")}, status_code=400)

    file_path = CONTENT_DIR / filename
    stem = Path(filename).stem

    # 既存ファイルの上書き禁止（サブディレクトリ含む再帰チェック）
    # アプリ側: FILE_NAME_CACHEは全ディレクトリのstem→pathマップ
    if stem in cache.FILE_NAME_CACHE:
        return JSONResponse({"status": "error", "message": get_error("E204")}, status_code=409)

    # ホスト側Vault: rglobで再帰的に同名ファイルを探索
    config = load_config()
    if config.content_src:
        host_src = Path(config.content_src)
        if host_src.exists() and any(host_src.rglob(filename)):
            return JSONResponse({"status": "error", "message": get_error("E204")}, status_code=409)

    # ファイル書き込み（アプリ内コンテンツ）
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    # ホスト側Vaultにも書き込み（同期設定がある場合）
    host_saved = False
    host_error = None
    host_path = Path(config.content_src) / filename if config.content_src else None
    if host_path:
        try:
            host_path.parent.mkdir(parents=True, exist_ok=True)
            with open(host_path, "w", encoding="utf-8") as f:
                f.write(content)
            host_saved = True
            logger.info("ホスト側Vaultに保存: %s", host_path)
        except Exception as e:
            host_error = str(e)
            logger.warning("ホスト側Vaultへの書き込みに失敗: %s", e)

    # キャッシュ更新
    refresh_global_caches()

    return {
        "status": "success",
        "message": get_system("S201"),
        "filename": filename,
        "host_saved": host_saved,
        "host_error": host_error,
    }
