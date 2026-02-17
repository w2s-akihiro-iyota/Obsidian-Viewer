from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import os
import math
from datetime import datetime, timezone, timedelta
from app.config import CONTENT_DIR, TEMPLATES_DIR
from app import cache
from app.core.indexing import get_all_files, get_file_tree, refresh_global_caches
from app.core.markdown import md, process_admonition_blocks
from app.services.images import process_obsidian_images
from app.services.sync import load_config, save_config, perform_sync
from app.events import config_updated_event
from app.utils.helpers import is_request_local, get_client_ip
from app.utils.messages import get_all_messages, get_error, get_warning

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["timestamp"] = int(datetime.now().timestamp())


@router.get("/api/preview")
async def preview_file(request: Request, path: str):
    # Safety check
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")
    
    full_path = CONTENT_DIR / path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Validation for non-localhost
    is_localhost = is_request_local(request)
    if not is_localhost:
        # We need to check if this file is published
        from app.core.indexing import parse_frontmatter
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        frontmatter, _ = parse_frontmatter(content)
        is_published = frontmatter.get('publish') is True or str(frontmatter.get('publish')).lower() == 'true'
        if not is_published:
            raise HTTPException(status_code=403, detail="Forbidden: This file is not public")
    else:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
    
    # Pre-process admonitions
    content = process_admonition_blocks(content)
    # Process Obsidian images
    content = process_obsidian_images(content)
    
    html = md.render(content)
    return HTMLResponse(content=html)

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
    PER_PAGE = 12
    total = len(filtered)
    pages = math.ceil(total / PER_PAGE)
    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    paginated_files = filtered[start:end]

    is_localhost = is_request_local(request)
    file_tree = cache.GLOBAL_FILE_TREE_CACHE if is_localhost else cache.GLOBAL_FILE_TREE_CACHE_PUBLIC

    return templates.TemplateResponse("index.html", {
        "request": request,
        "files": paginated_files,
        "file_tree": file_tree,
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
        
        from app.core.indexing import parse_frontmatter
        frontmatter, body = parse_frontmatter(content)
        title = frontmatter.get('title') or Path(file_path).stem
        
        # Pre-process admonitions
        body = process_admonition_blocks(body)
        # Process Obsidian images
        body = process_obsidian_images(body)
        
        html = md.render(body)
        # Update cache
        cache.MARKDOWN_CACHE[cache_key] = {
            'html': html,
            'title': title,
            'mtime': mtime,
            'frontmatter': frontmatter
        }

    is_localhost = is_request_local(request)
    file_tree = cache.GLOBAL_FILE_TREE_CACHE if is_localhost else cache.GLOBAL_FILE_TREE_CACHE_PUBLIC

    is_published = frontmatter.get('publish') is True or str(frontmatter.get('publish')).lower() == 'true'

    if not is_localhost and not is_published:
        raise HTTPException(status_code=403, detail="Forbidden: This file is not public")

    return templates.TemplateResponse("view.html", {
        "request": request,
        "title": title,
        "content": html,
        "file_path": file_path,
        "filename": Path(file_path).name,
        "file_tree": file_tree,
        "frontmatter": frontmatter,
        "is_published": is_published,
        "is_localhost": is_localhost
    })

@router.get("/api/messages")
async def api_get_messages():
    """
    フロントエンド用のメッセージ定義を返します。
    """
    return get_all_messages()

@router.post("/api/sync/save")
async def api_save_sync_settings(request: Request):
    if not is_request_local(request):
        return JSONResponse({"status": "error", "message": get_error("E101")}, status_code=403)
    
    data = await request.json()
    from app.models.sync import SyncConfig
    
    errors = {}
    warnings = {}
    
    # 1. Validation (Errors)
    content_src = data.get('content_src', '')
    if not content_src:
        errors['content-src'] = get_error("E001")
    else:
        p = Path(content_src)
        if not p.exists() or not p.is_dir():
            errors['content-src'] = get_error("E002")
            
    images_src = data.get('images_src', '')
    if images_src:
        p = Path(images_src)
        if not p.exists() or not p.is_dir():
            errors['images-src'] = get_error("E002")
            
    # 2. Warnings (Non-blocking)
    images_src_trimmed = images_src.strip()
    if not images_src_trimmed:
        warnings['images-src'] = get_warning("W001")

    base_url = data.get('base_url', '').strip()
    if not base_url:
        warnings['base-url'] = get_warning("W002")
        
    if errors:
        return JSONResponse({
            "status": "error",
            "errors": errors
        }, status_code=400)
    
    config = SyncConfig(**data)
    save_config(config)
    # 通知を送ってバックグラウンドタスクを起こす
    config_updated_event.set()
    
    return {
        "status": "success",
        "warnings": warnings
    }

@router.get("/api/sync/config")
async def api_get_sync_config(request: Request):
    if not is_request_local(request):
        return JSONResponse({"status": "error", "message": get_error("E101")}, status_code=403)
    config = load_config()
    return config

@router.get("/api/config")
async def api_get_public_config():
    # Publicly accessible safe config subset
    config = load_config()
    return {
        "base_url": config.base_url,
        "sync_enabled": config.sync_enabled
    }

@router.post("/api/sync/now")
@router.post("/api/sync")
async def api_sync_now(request: Request):
    if not is_request_local(request):
        return JSONResponse({"status": "error", "message": get_error("E101")}, status_code=403)
    from app.services.sync import load_config, perform_sync
    config = load_config()
    success, message = perform_sync(config)
    # 同期後、定期実行のタイマーをリセットさせるために通知を送る
    config_updated_event.set()
    if success:
        return {"status": "success", "last_sync": config.last_sync, "message": message}
    else:
        return JSONResponse({"status": "error", "message": message}, status_code=500)

@router.post("/api/reindex")
@router.post("/api/rebuild-index")
async def api_reindex(request: Request):
    if not is_request_local(request):
        return JSONResponse({"status": "error", "message": get_error("E101")}, status_code=403)
    
    refresh_global_caches()
    return {"status": "success"}

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
            
    return results[:10] # limit 10

@router.get("/api/dirs")
@router.get("/api/list-dirs")
async def list_dirs(request: Request, path: str = ""):
    if not is_request_local(request):
        return JSONResponse({"status": "error", "message": "Only local access allowed"}, status_code=403)
    
    try:
        if not path:
            if os.name == 'nt': # Windows
                import ctypes
                drives = []
                bitmask = ctypes.windll.kernel32.GetLogicalDrives()
                for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                    if bitmask & 1:
                        drive = f"{letter}:\\"
                        drives.append({"name": drive, "path": drive})
                    bitmask >>= 1
                return {"current": "", "dirs": drives, "is_root": True}
            else:
                path = "/"

        p = Path(path)
        if not p.exists():
            return {"current": path, "dirs": [], "parent": str(p.parent)}

        dirs = [
            {"name": d.name, "path": str(d.absolute())} 
            for d in p.iterdir() if d.is_dir() and not d.name.startswith('.')
        ]
        dirs.sort(key=lambda x: x['name'].lower())
        return {
            "current": str(p),
            "dirs": dirs,
            "parent": str(p.parent) if p.parent != p else None
        }
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
