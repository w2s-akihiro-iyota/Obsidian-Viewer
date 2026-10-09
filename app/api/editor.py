"""エディタ系エンドポイント（localhost限定）"""
# Standard library
import logging
from pathlib import Path

# Third party
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse

# Local
from app.api import templates

logger = logging.getLogger("app.editor")
from app import cache
from app.config import CONTENT_DIR
from app.core.indexing import parse_frontmatter, refresh_global_caches
from app.services.content import render_markdown
from app.services.note_editing import (
    NoteConflictError, NoteNotFoundError, NoteWriteError, VaultWriteError, load_note, save_note,
)
from app.services.sync import load_config
from app.utils.helpers import is_admin_request, admin_guard
from app.utils.messages import get_error, get_system

router = APIRouter()


@router.get("/editor", response_class=HTMLResponse)
async def editor_page(request: Request, path: str = ""):
    """
    エディタページを表示する（localhost限定）

    path（スラッグまたは実パス）を渡すと既存ノートの編集、無ければ新規作成として開く。
    """
    if not is_admin_request(request):
        raise HTTPException(status_code=403, detail=get_error("E101"))

    edit_path = ""
    edit_slug = ""
    if path:
        edit_path = cache.SLUG_TO_PATH.get(path, path)
        if edit_path not in cache.PATH_TO_SLUG:
            raise HTTPException(status_code=404, detail=get_error("E205"))
        edit_slug = cache.PATH_TO_SLUG[edit_path]

    return templates.TemplateResponse(request=request, name="editor.html", context={
        "request": request,
        "is_localhost": True,
        "edit_path": edit_path,
        "edit_slug": edit_slug,
    })


@router.get("/api/editor/note")
async def editor_load_note(request: Request, path: str):
    """既存ノートの中身と、衝突検知用のハッシュを返す（localhost限定）"""
    if error := admin_guard(request): return error

    try:
        content, digest = load_note(path)
    except NoteNotFoundError:
        return JSONResponse({"status": "error", "message": get_error("E205")}, status_code=404)
    return {"status": "success", "path": path, "content": content, "hash": digest}


@router.post("/api/editor/update")
async def editor_update_note(request: Request):
    """既存ノートを上書き保存する（localhost限定）。開いたあとに更新されていたら 409"""
    if error := admin_guard(request): return error

    data = await request.json()
    path = data.get("path", "")
    content = data.get("content", "")
    base_hash = data.get("base_hash", "")
    force = data.get("force") is True

    try:
        result = save_note(path, content, base_hash, force=force)
    except NoteNotFoundError:
        return JSONResponse({"status": "error", "message": get_error("E205")}, status_code=404)
    except ValueError:
        return JSONResponse({"status": "error", "message": get_error("E203")}, status_code=400)
    except NoteConflictError as e:
        return JSONResponse(
            {"status": "conflict", "message": get_error("E206"), "current_hash": e.current_hash},
            status_code=409
        )
    except VaultWriteError as e:
        logger.warning("ホスト側Vaultへの書き込みに失敗: %s", e)
        return JSONResponse({"status": "error", "message": get_error("E207")}, status_code=500)
    except NoteWriteError as e:
        logger.warning("ノートの書き込みに失敗: %s", e)
        return JSONResponse({"status": "error", "message": get_error("E208")}, status_code=500)

    logger.info("ノートを更新: %s (Vault=%s, ビューア=%s)", path, result.host_saved, result.app_saved)
    # 全体の作り直しは重いので、別スレッドで行ってほかのリクエストを止めない
    # ファイルは保存済みなので、作り直しに失敗しても保存の成功として返す（次の同期・再構築で反映される）
    try:
        await run_in_threadpool(refresh_global_caches)
    except Exception as e:
        logger.warning("保存後のキャッシュ再構築に失敗: %s", e, exc_info=True)

    return {
        "status": "success",
        "message": get_system("S202"),
        "hash": result.hash,
        "host_saved": result.host_saved,
        "app_saved": result.app_saved,
        "slug": cache.PATH_TO_SLUG.get(path, path),
    }


@router.post("/api/editor/preview")
async def editor_preview(request: Request):
    """Markdownプレビューを返す（localhost限定）"""
    if error := admin_guard(request): return error

    data = await request.json()
    content = data.get("content", "")

    if not content.strip():
        return HTMLResponse(content="<p style='color:var(--text-muted);'>プレビューするコンテンツがありません</p>")

    try:
        # 記事ページと同じ見た目にするため、frontmatter は除いて本文だけを描画する
        _, body = parse_frontmatter(content)
        html = render_markdown(body, published_only=False)
    except Exception as e:
        logger.error("Preview render error: %s", e)
        html = f"<p style='color:#ff6b6b;'>レンダリングエラー: {e}</p>"

    return HTMLResponse(content=html)


@router.post("/api/editor/save")
async def editor_save(request: Request):
    """Markdownファイルを保存する（localhost限定）"""
    if error := admin_guard(request): return error

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
