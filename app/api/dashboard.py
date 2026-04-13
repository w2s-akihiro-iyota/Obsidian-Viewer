"""ダッシュボード エンドポイント（localhost限定）"""
from collections import Counter

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from app import cache
from app.api import templates
from app.utils.helpers import is_request_local

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """ダッシュボードページ（localhost限定）"""
    if not is_request_local(request):
        raise HTTPException(status_code=403, detail="Forbidden")

    files = cache.GLOBAL_FILE_CACHE

    # 統計情報
    total_files = len(files)
    public_files = sum(1 for f in files if f.get("published"))
    private_files = total_files - public_files
    total_chars = sum(f.get("char_count", 0) for f in files)

    # タグ分布 (top 20)
    tag_counter = Counter()
    for f in files:
        for t in (f.get("tags") or []):
            tag_counter[t] += 1
    top_tags = tag_counter.most_common(20)
    max_tag_count = top_tags[0][1] if top_tags else 1

    # 最近更新されたファイル (top 10)
    recent_files = files[:10]

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "request": request,
        "is_localhost": True,
        "total_files": total_files,
        "public_files": public_files,
        "private_files": private_files,
        "total_chars": total_chars,
        "top_tags": top_tags,
        "max_tag_count": max_tag_count,
        "recent_files": recent_files
    })
