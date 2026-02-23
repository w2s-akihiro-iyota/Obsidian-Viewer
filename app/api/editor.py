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
    is_overwrite = file_path.exists()

    # ファイル書き込み（アプリ内コンテンツ）
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    # ホスト側Vaultにも書き込み（同期設定がある場合）
    config = load_config()
    if config.content_src:
        host_path = Path(config.content_src) / filename
        try:
            with open(host_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            logger.warning("ホスト側Vaultへの書き込みに失敗: %s", e)

    # キャッシュ更新
    refresh_global_caches()

    message = get_system("S202") if is_overwrite else get_system("S201")
    return {"status": "success", "message": message, "filename": filename}
