"""コンテンツ表示・検索系エンドポイント"""
# Standard library
import math
import re
import time
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
from app.services.images import find_image_in_static
from app.utils.helpers import is_request_local
from app.utils.messages import get_all_messages

router = APIRouter()


def _get_related_articles(file_path: str, tags: list, is_localhost: bool, limit: int = 5) -> list[dict]:
    """タグの共通度に基づいて関連記事を取得"""
    if not tags:
        return []

    tag_set = set(tags)
    scored = []

    for f in cache.GLOBAL_FILE_CACHE:
        if f["path"] == file_path:
            continue
        if not is_localhost and not f.get("published"):
            continue

        other_tags = set(f.get("tags") or [])
        common = len(tag_set & other_tags)
        if common > 0:
            scored.append({
                "title": f["title"],
                "path": f["path"],
                "score": common
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


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
        "is_localhost": is_localhost,
        "og_url": str(request.url)
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

    # キャッシュから読了時間を取得
    reading_time = 1
    for f in cache.GLOBAL_FILE_CACHE:
        if f["path"] == file_path:
            reading_time = f.get("reading_time", 1)
            break

    # OGP用のdescription生成
    description = frontmatter.get("description", "")
    raw_body = ""
    og_image_from_fm = frontmatter.get("image") or frontmatter.get("thumbnail")
    if not description or not og_image_from_fm:
        with open(full_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
        _, raw_body = parse_frontmatter(raw_content)

    if not description:
        # body先頭からプレーンテキスト150文字を抽出
        plain = re.sub(r'<[^>]+>', '', raw_body)
        plain = re.sub(r'[#*_~`>\-\|\[\]!()]', '', plain)
        plain = plain.replace('\n', ' ').strip()[:150]
        description = plain

    og_url = str(request.url)
    base_url = str(request.base_url).rstrip('/')

    # OGP画像の抽出
    og_image = og_image_from_fm
    if not og_image and raw_body:
        # Obsidianの画像記法 ![[image.png]] または ![[image.png|300]] を探す
        obs_match = re.search(r'!\[\[([^|\]]+?)(?:\|[^\]]*)?\]\]', raw_body)
        if obs_match:
            resolved = find_image_in_static(obs_match.group(1).strip())
            if resolved:
                og_image = resolved
        if not og_image:
            # Markdownの画像構文 ![alt](url) を探す
            img_match = re.search(r'!\[.*?\]\((.*?)\)', raw_body)
            if img_match:
                og_image = img_match.group(1)
            else:
                # HTMLのimgタグ構文 <img src="url"> を探す
                img_html_match = re.search(r'<img[^>]+src=["\'](.*?)["\']', raw_body)
                if img_html_match:
                    og_image = img_html_match.group(1)

    # og_imageが相対パス(local)の場合は絶対URLに変換
    if og_image and not og_image.startswith(('http://', 'https://')):
        if not og_image.startswith('/'):
            og_image = '/' + og_image
        og_image = base_url + og_image

    # バックリンク取得
    backlinks = cache.BACKLINK_CACHE.get(file_path, [])
    # 非localhostの場合、公開ファイルのみに絞る
    if not is_localhost:
        published_paths = {f["path"] for f in cache.GLOBAL_FILE_CACHE if f.get("published")}
        backlinks = [bl for bl in backlinks if bl["path"] in published_paths]

    # 関連記事取得
    tags = frontmatter.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    related_articles = _get_related_articles(file_path, tags, is_localhost)

    return templates.TemplateResponse("view.html", {
        "request": request,
        "title": title,
        "content": html,
        "file_path": file_path,
        "filename": Path(file_path).name,
        "frontmatter": frontmatter,
        "is_published": is_pub,
        "is_localhost": is_localhost,
        "reading_time": reading_time,
        "description": description,
        "og_url": og_url,
        "og_image": og_image,
        "backlinks": backlinks,
        "related_articles": related_articles
    })


@router.get("/api/messages")
async def api_get_messages():
    """フロントエンド用のメッセージ定義を返します。"""
    return get_all_messages()


def _legacy_search(q: str, is_localhost: bool) -> list[dict]:
    """旧方式の線形スキャン検索（ベンチマーク比較用に抽出）"""
    q_lower = q.lower()
    results = []

    for f in cache.GLOBAL_FILE_CACHE:
        if not is_localhost and not f.get('published'):
            continue

        match_type = None
        snippet = ""

        if q_lower in f['title'].lower():
            match_type = "title"
        elif q_lower in f['path'].lower():
            match_type = "path"
        elif q_lower in f.get('body_text', '').lower():
            match_type = "body"
            body = f.get('body_text', '')
            idx = body.lower().find(q_lower)
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(body), idx + len(q) + 50)
                snippet = ("..." if start > 0 else "") + body[start:end] + ("..." if end < len(body) else "")

        if match_type:
            results.append({
                "title": f['title'],
                "path": f['path'],
                "match_type": match_type,
                "snippet": snippet
            })

    return results[:20]


@router.get("/api/search")
async def api_search(request: Request, q: str = ""):
    if not q:
        return []

    is_localhost = is_request_local(request)

    # TF-IDFインデックスが構築済みなら新方式を使用
    if cache.SEARCH_INDEX is not None:
        return cache.SEARCH_INDEX.search(q, is_localhost, cache.GLOBAL_FILE_CACHE)

    # フォールバック: 旧方式
    return _legacy_search(q, is_localhost)


@router.get("/api/search/benchmark")
async def api_search_benchmark(request: Request):
    """旧方式と新方式の検索パフォーマンスを比較（localhost限定）"""
    if not is_request_local(request):
        raise HTTPException(status_code=403, detail="Forbidden")

    if cache.SEARCH_INDEX is None:
        return {"error": "検索インデックスが未構築です"}

    test_queries = [
        "python",
        "docker compose",
        "環境構築",
        "API",
        "設定",
        "データベース",
        "test",
        "Linux コマンド",
        "セキュリティ",
        "error handling",
    ]

    results = []
    for q in test_queries:
        # 旧方式
        t0 = time.perf_counter()
        old_results = _legacy_search(q, is_localhost=True)
        old_time = (time.perf_counter() - t0) * 1000  # ms

        # 新方式
        t0 = time.perf_counter()
        new_results = cache.SEARCH_INDEX.search(q, True, cache.GLOBAL_FILE_CACHE)
        new_time = (time.perf_counter() - t0) * 1000  # ms

        results.append({
            "query": q,
            "legacy": {
                "time_ms": round(old_time, 3),
                "count": len(old_results),
                "top3": [r["title"] for r in old_results[:3]],
            },
            "tfidf": {
                "time_ms": round(new_time, 3),
                "count": len(new_results),
                "top3": [r["title"] for r in new_results[:3]],
            },
        })

    # 集計
    legacy_avg = sum(r["legacy"]["time_ms"] for r in results) / len(results)
    tfidf_avg = sum(r["tfidf"]["time_ms"] for r in results) / len(results)
    speedup = legacy_avg / tfidf_avg if tfidf_avg > 0 else float("inf")

    return {
        "benchmark": results,
        "summary": {
            "legacy_avg_ms": round(legacy_avg, 3),
            "tfidf_avg_ms": round(tfidf_avg, 3),
            "speedup_ratio": round(speedup, 2),
            "doc_count": cache.SEARCH_INDEX.doc_count,
            "vocab_size": len(cache.SEARCH_INDEX.inverted_index),
        }
    }
