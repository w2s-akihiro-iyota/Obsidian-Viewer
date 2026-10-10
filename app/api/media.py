"""Vault の添付（MEDIA_DIR）の配信（S-5）

管理者には全部を返す。外部の人にはアプリ同梱のサンプルと、公開ノートが参照する添付（cache.PUBLIC_MEDIA_PATHS）だけを返す。
見せないものは 403 ではなく 404 にする（存在を知らせない）。

添付は Vault の中身なので、HTML や SVG が混ざっていてもこのサイトの権限でスクリプトを動かさない:
- すべての応答に nosniff と CSP sandbox を付ける（直接開いてもスクリプト・フォームを止める）
- 画面に埋め込む画像（MEDIA_INLINE_EXTS）以外は Content-Disposition: attachment でダウンロードにする
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app import cache
from app.config import MEDIA_DIR, MEDIA_INLINE_EXTS
from app.services.images import MEDIA_URL_PREFIX
from app.services.media_access import is_public_media, resolve_media_file
from app.utils.helpers import is_admin_request

router = APIRouter()

# 添付の応答に必ず付けるヘッダー
_MEDIA_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox",
}


@router.api_route(MEDIA_URL_PREFIX + "{path:path}", methods=["GET", "HEAD"])
async def get_media(request: Request, path: str):
    resolved = resolve_media_file(MEDIA_DIR, path)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Not found")
    target, rel_path = resolved

    if not is_admin_request(request) and not is_public_media(rel_path, cache.PUBLIC_MEDIA_PATHS, cache.MEDIA_INDEX):
        raise HTTPException(status_code=404, detail="Not found")

    ext = target.suffix.lower().lstrip('.')
    inline = ext in MEDIA_INLINE_EXTS
    return FileResponse(target, headers=_MEDIA_SECURITY_HEADERS,
                        filename=None if inline else target.name,
                        content_disposition_type="inline" if inline else "attachment")
