"""コンテンツ表示・検索系エンドポイント"""
# Standard library
import math
from pathlib import Path

# Third party
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

# Local
from app import cache
from app.api import templates
from app.config import CONTENT_DIR, PER_PAGE
from app.core.indexing import parse_frontmatter, is_published
from app.services.content import render_markdown
from app.utils.helpers import is_request_local
from app.utils.messages import get_all_messages

router = APIRouter()


@router.get("/api/preview")
async def preview_file(request: Request, path: str):
    # Safety check
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    full_path = CONTENT_DIR / path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Validation for non-localhost
    is_localhost = is_request_local(request)
    if not is_localhost:
        frontmatter, _ = parse_frontmatter(content)
        if not is_published(frontmatter):
            raise HTTPException(status_code=403, detail="Forbidden: This file is not public")

    # frontmatterからタイトルを取得
    frontmatter, body = parse_frontmatter(content)
    title = frontmatter.get("title") or Path(path).stem

    html = render_markdown(body)
    return JSONResponse(content={"title": title, "content": html})


@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request, page: int = 1, q: str = "", tag: str = "", visibility: str = "all"):
    # Filter files
    filtered = cache.GLOBAL_FILE_CACHE

    if q:
        q_lower = q.lower()
        filtered = [f for f in filtered if q_lower in f['title'].lower() or q_lower in f['path'].lower()]

    if tag:
        filtered = [f for f in filtered if tag in (f.get('tags') or [])]

    if not is_request_local(request):
        # Force public visibility for external requests
        filtered = [f for f in filtered if f.get('published')]
    else:
        if visibility == "public":
            filtered = [f for f in filtered if f.get('published')]
        elif visibility == "private":
            filtered = [f for f in filtered if not f.get('published')]

    # Tags for cloud
    all_tags = set()
    for f in cache.GLOBAL_FILE_CACHE:
        for t in (f.get('tags') or []):
            all_tags.add(t)
    all_tags = sorted(list(all_tags))

    # Pagination
    total = len(filtered)
    pages = math.ceil(total / PER_PAGE)
    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    paginated_files = filtered[start:end]

    is_localhost = is_request_local(request)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "files": paginated_files,
        "total_items": total,
        "current_page": page,
        "total_pages": pages,
        "selected_tag": tag,
        "all_tags": all_tags,
        "visibility": visibility,
        "q": q,
        "is_localhost": is_localhost
    })


@router.get("/view/{file_path:path}", response_class=HTMLResponse)
async def read_item(request: Request, file_path: str):
    full_path = CONTENT_DIR / file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    mtime = full_path.stat().st_mtime

    # Check cache
    cache_key = str(file_path)
    if cache_key in cache.MARKDOWN_CACHE and cache.MARKDOWN_CACHE[cache_key]['mtime'] == mtime:
        entry = cache.MARKDOWN_CACHE[cache_key]
        html = entry['html']
        title = entry['title']
        frontmatter = entry.get('frontmatter', {})
    else:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        frontmatter, body = parse_frontmatter(content)
        title = frontmatter.get('title') or Path(file_path).stem

        html = render_markdown(body)
        # Update cache
        cache.MARKDOWN_CACHE[cache_key] = {
            'html': html,
            'title': title,
            'mtime': mtime,
            'frontmatter': frontmatter
        }

    is_localhost = is_request_local(request)

    is_pub = is_published(frontmatter)

    if not is_localhost and not is_pub:
        raise HTTPException(status_code=403, detail="Forbidden: This file is not public")

    return templates.TemplateResponse("view.html", {
        "request": request,
        "title": title,
        "content": html,
        "file_path": file_path,
        "filename": Path(file_path).name,
        "frontmatter": frontmatter,
        "is_published": is_pub,
        "is_localhost": is_localhost
    })


@router.get("/api/messages")
async def api_get_messages():
    """フロントエンド用のメッセージ定義を返します。"""
    return get_all_messages()


@router.get("/api/search")
async def api_search(request: Request, q: str = ""):
    if not q:
        return []

    is_localhost = is_request_local(request)
    q_lower = q.lower()
    results = []

    for f in cache.GLOBAL_FILE_CACHE:
        if not is_localhost and not f.get('published'):
            continue

        if q_lower in f['title'].lower() or q_lower in f['path'].lower():
            results.append({"title": f['title'], "path": f['path']})

    return results[:10]  # limit 10
