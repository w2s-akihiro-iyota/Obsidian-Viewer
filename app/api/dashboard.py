"""ダッシュボード エンドポイント（localhost限定）"""
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from app import cache
from app.api import templates
from app.config import DASHBOARD_HEALTH_ROW_LIMIT, DASHBOARD_HEATMAP_WEEKS, DASHBOARD_TOP_TAG_COUNT
from app.core.heatmap import HEATMAP_LEVEL_COUNT, build_heatmap
from app.core.note_health import build_note_health
from app.core.note_list import count_tags
from app.utils.helpers import is_admin_request

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """ダッシュボードページ（localhost限定）"""
    if not is_admin_request(request):
        raise HTTPException(status_code=403, detail="Forbidden")

    files = cache.GLOBAL_FILE_CACHE

    # 統計情報
    total_files = len(files)
    public_files = sum(1 for f in files if f.get("published"))
    private_files = total_files - public_files
    total_chars = sum(f.get("char_count", 0) for f in files)

    # タグ分布（件数の多い順に上位だけ）
    top_tags = count_tags(files).most_common(DASHBOARD_TOP_TAG_COUNT)
    max_tag_count = top_tags[0][1] if top_tags else 1

    # 最近更新されたファイル (top 10)
    recent_files = files[:10]

    # 手入れが必要なノート（F-6）。索引の作り直しで作ったキャッシュだけから数える
    health = build_note_health(files, cache.BACKLINK_CACHE, DASHBOARD_HEALTH_ROW_LIMIT)

    heatmap_data, month_labels = build_heatmap(files, datetime.now())

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "request": request,
        "is_localhost": True,
        "total_files": total_files,
        "public_files": public_files,
        "private_files": private_files,
        "total_chars": total_chars,
        "top_tags": top_tags,
        "max_tag_count": max_tag_count,
        "recent_files": recent_files,
        "health": health,
        "heatmap_data": heatmap_data,
        "heatmap_weeks": DASHBOARD_HEATMAP_WEEKS,
        "heatmap_level_count": HEATMAP_LEVEL_COUNT,
        "month_labels": month_labels,
    })
