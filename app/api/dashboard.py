"""ダッシュボード エンドポイント（localhost限定）"""
from collections import Counter
from datetime import datetime, timedelta

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

    # ヒートマップ用のデータ生成
    now = datetime.now()
    start_date = now - timedelta(days=365)
    # 日曜始まりに調整
    days_since_sunday = (start_date.weekday() + 1) % 7
    start_date = start_date - timedelta(days=days_since_sunday)
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    daily_chars = {}
    for f in files:
        updated_str = f.get("updated")
        if updated_str:
            try:
                # "2026-04-14 10:17" や "2026-04-14 10:17:00" などに対応するためスライス
                date_str = updated_str[:10]
                daily_chars[date_str] = daily_chars.get(date_str, 0) + f.get("char_count", 0)
            except Exception:
                pass

    heatmap_data = []
    month_labels = []
    last_month = None

    current_date = start_date
    days_count = (now - start_date).days + 1

    for i in range(days_count):
        d_str = current_date.strftime("%Y-%m-%d")
        
        # 月が変わったタイミング（または最初）でラベルに追加
        if current_date.month != last_month:
            month_labels.append(current_date.strftime("%Y/%m"))
            last_month = current_date.month

        chars = daily_chars.get(d_str, 0)
        
        if chars == 0:
            level = 0
        elif chars <= 1000:
            level = 1
        elif chars <= 3000:
            level = 2
        elif chars <= 5000:
            level = 3
        else:
            level = 4
            
        heatmap_data.append({
            "date": d_str,
            "count": chars,
            "level": level
        })
        current_date += timedelta(days=1)

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
        "heatmap_data": heatmap_data,
        "month_labels": month_labels
    })
