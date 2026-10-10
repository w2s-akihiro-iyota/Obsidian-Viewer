"""コンテンツ表示・検索系エンドポイント"""
# Standard library
import math
import re
import time
from dataclasses import replace
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Callable
from urllib.parse import quote

# Third party
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

# Local
from app import cache
from app.api import templates
from app.config import CONTENT_DIR, JST, LIST_TOP_TAG_COUNT, LOCAL_GRAPH_DEPTHS, PER_PAGE, SEARCH_LIMIT
from app.core.graph import build_link_graph, neighbor_count
from app.core.indexing import parse_frontmatter, is_published
from app.core.note_list import DEFAULT_SORT, LIST_SORTS, LIST_VISIBILITIES, ListQuery, build_note_list
from app.core.search import parse_search_query
from app.services.content import render_markdown
from app.services.media_access import first_image_href
from app.services.publish_check import check_publish
from app.utils.helpers import is_admin_request, is_public_view
from app.utils.messages import get_all_messages

router = APIRouter()


def _mtimes(paths: set[str]) -> dict[str, float | None]:
    """埋め込んだノートの更新日時（消えていれば None）"""
    result = {}
    for p in paths:
        try:
            result[p] = (CONTENT_DIR / p).stat().st_mtime
        except OSError:
            result[p] = None
    return result


_LEADING_H1_RE = re.compile(r'\s*<h1(?P<attrs>[^>]*)>(?P<inner>.*?)</h1>', re.DOTALL)


def _mark_duplicate_title(html: str, title: str) -> str:
    """
    本文の最初のブロックが h1 で、文字がヘッダーのタイトルと同じなら、本文側の h1 に class を付けて見えなくする

    id は残す（目次から飛べるように）。対象はページ本文の先頭だけで、埋め込みの中の h1 は見ない
    （埋め込みは先頭が <div class="markdown-embed"> になるので当たらない）。
    """
    m = _LEADING_H1_RE.match(html)
    if not m or 'class=' in m.group('attrs'):
        return html
    text = unescape(re.sub(r'<[^>]+>', '', m.group('inner'))).strip()
    if text != str(title).strip():
        return html
    return html[:m.start('attrs')] + ' class="view-title-duplicate"' + html[m.start('attrs'):]


def _breadcrumbs(file_path: str) -> list[dict]:
    """パンくずのフォルダ部分。フォルダ名と、そのフォルダまでのパスで一覧を絞り込む URL（/?q=フォルダ/）"""
    folders = Path(file_path).parent.parts
    return [
        {"name": name, "href": "/?q=" + quote("/".join(folders[:i + 1]) + "/", safe="")}
        for i, name in enumerate(folders)
    ]


def _og_description(frontmatter: dict, body: str) -> str:
    """OGP の description。frontmatter に無ければ本文の先頭からプレーンテキスト 150 文字"""
    description = frontmatter.get("description", "")
    if description:
        return description
    plain = re.sub(r'<[^>]+>', '', body)
    plain = re.sub(r'[#*_~`>\-\|\[\]!()]', '', plain)
    return plain.replace('\n', ' ').strip()[:150]


def _get_related_articles(file_path: str, tags: list, published_only: bool, limit: int = 5) -> list[dict]:
    """タグの共通度に基づいて関連記事を取得（published_only なら公開ノートだけ）"""
    if not tags:
        return []

    tag_set = set(tags)
    scored = []

    for f in cache.GLOBAL_FILE_CACHE:
        if f["path"] == file_path:
            continue
        if published_only and not f.get("published"):
            continue

        other_tags = set(f.get("tags") or [])
        common = len(tag_set & other_tags)
        if common > 0:
            scored.append({
                "title": f["title"],
                "path": f["path"],
                "slug": cache.PATH_TO_SLUG.get(f["path"], f["path"]),
                "score": common
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


@router.get("/api/preview")
async def preview_file(request: Request, path: str):
    # Safety check
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    # スラッグからの解決を試みる
    resolved = cache.SLUG_TO_PATH.get(path)
    if resolved:
        path = resolved

    full_path = CONTENT_DIR / path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    frontmatter, body = parse_frontmatter(content)

    # Validation for non-localhost
    is_localhost = is_admin_request(request)
    if not is_localhost and not is_published(frontmatter):
        raise HTTPException(status_code=403, detail="Forbidden: This file is not public")

    # frontmatterからタイトルを取得
    title = frontmatter.get("title") or Path(path).stem

    html = render_markdown(body, published_only=not is_localhost, source_path=path)
    return JSONResponse(content={"title": title, "content": html})


@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request, page: int = 1, q: str = "", tag: str = "", visibility: str = "all",
                    sort: str = DEFAULT_SORT):
    """
    トップのノート一覧

    検索語 q・タグ・公開状態（管理者だけ）で絞り込み、sort で並べ替える（app/core/note_list.py）。
    """
    is_localhost = is_admin_request(request)
    query = ListQuery.from_params(q=q, tag=tag, visibility=visibility, sort=sort, page=page, is_admin=is_localhost)
    note_list = build_note_list(cache.GLOBAL_FILE_CACHE, query, is_admin=is_localhost,
                                top_tag_count=LIST_TOP_TAG_COUNT)

    # ページ送り。総ページ数を超えたら最後のページに丸める（0件なら1）
    total = len(note_list.files)
    pages = math.ceil(total / PER_PAGE)
    query = replace(query, page=min(query.page, max(pages, 1)))
    start = (query.page - 1) * PER_PAGE
    paginated_files = note_list.files[start:start + PER_PAGE]

    return templates.TemplateResponse(request=request, name="index.html", context={
        "request": request,
        "files": paginated_files,
        "total_items": total,
        "total_pages": pages,
        "query": query,
        "note_list": note_list,
        "visibility_options": LIST_VISIBILITIES,
        "sort_options": {k: v[0] for k, v in LIST_SORTS.items()},
        "is_localhost": is_localhost,
        "og_url": str(request.url)
    })


@router.get("/view/{file_path:path}", response_class=HTMLResponse)
async def read_item(request: Request, file_path: str, view_as: str = Query("", alias="as")):
    """
    記事ページ

    管理者は ?as=public で「外部の人の表示」（外部向けと同じ本文と、公開チェックの結果）を見られる。
    外部の人が ?as=public を付けても何も変わらない。
    """
    # スラッグからの解決を試みる
    actual_path = cache.SLUG_TO_PATH.get(file_path)
    if actual_path is None:
        # レガシーパス（実ファイルパス）でのアクセス → スラッグURLへ301リダイレクト
        full_path = CONTENT_DIR / file_path
        if full_path.exists() and full_path.is_file():
            slug = cache.PATH_TO_SLUG.get(file_path)
            if slug:
                return RedirectResponse(url=f"/view/{slug}", status_code=301)
            actual_path = file_path
        else:
            raise HTTPException(status_code=404, detail="File not found")
    file_path = actual_path

    full_path = CONTENT_DIR / file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    mtime = full_path.stat().st_mtime
    is_localhost = is_admin_request(request)
    # 本文・バックリンク・関連記事を公開ノートだけに絞るか（外部の人と、管理者の外部表示）
    published_only = is_public_view(request, view_as)
    # 管理者が外部の人の表示を確かめているとき
    public_view = is_localhost and published_only

    # Check cache
    # 外部向けは Dataview の結果が変わるため、閲覧者の種類ごとに別のキャッシュにする
    cache_key = (str(file_path), published_only)
    entry = cache.MARKDOWN_CACHE.get(cache_key)
    # 自分の更新日時に加えて、埋め込んだノートの更新日時も変わっていなければキャッシュを使う
    if not (entry and entry['mtime'] == mtime and _mtimes(set(entry['deps'])) == entry['deps']):
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        frontmatter, body = parse_frontmatter(content)
        deps: set[str] = set()
        # 公開チェック（本文）と OGP（description・画像の元）に要るものも一緒に覚え、表示のたびに読み直さない
        entry = {
            'html': render_markdown(body, published_only=published_only, deps=deps, source_path=file_path),
            'title': frontmatter.get('title') or Path(file_path).stem,
            'mtime': mtime,
            'frontmatter': frontmatter,
            'deps': _mtimes(deps),
            'body': body,
            'description': _og_description(frontmatter, body),
            # 許可リストと同じ抽出で選ぶ（外部の人に 404 になる画像を OGP にしない）
            'og_image': first_image_href(frontmatter, body, cache.MEDIA_INDEX),
        }
        cache.MARKDOWN_CACHE[cache_key] = entry

    html = entry['html']
    title = entry['title']
    frontmatter = entry['frontmatter']

    is_pub = is_published(frontmatter)

    # 403 は外部の人だけ。管理者の外部表示では、403 になることを画面で知らせる
    if not is_localhost and not is_pub:
        raise HTTPException(status_code=403, detail="Forbidden: This file is not public")

    # 公開チェックは管理者にだけ行う（外部の人には計算もしない）
    publish_check = None
    if is_localhost:
        publish_check = check_publish(file_path, entry['body'], is_pub)

    # キャッシュから読了時間を取得
    reading_time = 1
    for f in cache.GLOBAL_FILE_CACHE:
        if f["path"] == file_path:
            reading_time = f.get("reading_time", 1)
            break

    # OGP（description と画像の元は描画のときに作ってキャッシュに入れてある）
    description = entry['description']
    og_image = entry['og_image']
    og_url = str(request.url)
    base_url = str(request.base_url).rstrip('/')

    # og_imageが相対パス(local)の場合は絶対URLに変換
    if og_image and not og_image.startswith(('http://', 'https://')):
        if not og_image.startswith('/'):
            og_image = '/' + og_image
        og_image = base_url + og_image

    # バックリンク取得
    backlinks = cache.BACKLINK_CACHE.get(file_path, [])
    # 外部の人（と管理者の外部表示）には、公開ファイルのみに絞る
    if published_only:
        published_paths = {f["path"] for f in cache.GLOBAL_FILE_CACHE if f.get("published")}
        backlinks = [bl for bl in backlinks if bl["path"] in published_paths]

    # 関連記事取得
    tags = frontmatter.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    related_articles = _get_related_articles(file_path, tags, published_only)

    slug = cache.PATH_TO_SLUG.get(file_path, file_path)

    # つながりのボタンの数（1 歩でつながっているノート）。外部表示では公開ノートだけで数える（/api/graph と同じ範囲）
    link_graph = build_link_graph(cache.GLOBAL_FILE_CACHE, cache.FORWARD_LINK_CACHE, published_only)
    local_graph_count = neighbor_count(link_graph, file_path)

    return templates.TemplateResponse(request=request, name="view.html", context={
        "request": request,
        "title": title,
        "content": _mark_duplicate_title(html, title),
        "file_path": file_path,
        "slug": slug,
        "breadcrumbs": _breadcrumbs(file_path),
        "updated": datetime.fromtimestamp(mtime, JST),
        "frontmatter": frontmatter,
        "is_published": is_pub,
        # 外部表示中は、編集メニューなどを外部の人と同じく出さない
        "is_localhost": is_localhost and not public_view,
        "is_admin": is_localhost,
        "public_view": public_view,
        "publish_check": publish_check,
        "reading_time": reading_time,
        "description": description,
        "og_url": og_url,
        "og_image": og_image,
        "backlinks": backlinks,
        "related_articles": related_articles,
        "local_graph_depths": LOCAL_GRAPH_DEPTHS,
        "local_graph_count": local_graph_count,
    })


@router.get("/api/messages")
async def api_get_messages():
    """フロントエンド用のメッセージ定義を返します。"""
    return get_all_messages()


def _legacy_search(q: str, is_localhost: bool, accept: Callable[[dict], bool] | None = None) -> list[dict]:
    """旧方式の線形スキャン検索（ベンチマーク比較用に抽出）"""
    q_lower = q.lower()
    results = []

    for f in cache.GLOBAL_FILE_CACHE:
        if not is_localhost and not f.get('published'):
            continue
        if accept is not None and not accept(f):
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
                "slug": cache.PATH_TO_SLUG.get(f['path'], f['path']),
                "match_type": match_type,
                "snippet": snippet
            })

    return results[:SEARCH_LIMIT]


@router.get("/api/search")
async def api_search(request: Request, q: str = ""):
    query = parse_search_query(q)
    if not query.text and not query.has_filters:
        return []

    is_localhost = is_admin_request(request)
    accept = query.matches if query.has_filters else None

    # 絞り込みだけ（tag:会議 など）のときは、条件に合うノートを新しい順に返す
    if not query.text:
        return [
            {
                "title": f["title"],
                "path": f["path"],
                "slug": cache.PATH_TO_SLUG.get(f["path"], f["path"]),
                "snippet": "",
            }
            for f in cache.GLOBAL_FILE_CACHE
            if (is_localhost or f.get("published")) and query.matches(f)
        ][:SEARCH_LIMIT]

    # TF-IDFインデックスが構築済みなら新方式を使用
    if cache.SEARCH_INDEX is not None:
        return cache.SEARCH_INDEX.search(query.text, is_localhost, cache.GLOBAL_FILE_CACHE,
                                         limit=SEARCH_LIMIT, accept=accept)

    # フォールバック: 旧方式
    return _legacy_search(query.text, is_localhost, accept)


@router.get("/api/tree")
async def api_tree(request: Request):
    """サイドバーのファイルツリー（外部からは公開ノートだけの木）"""
    if is_admin_request(request):
        return cache.GLOBAL_FILE_TREE_CACHE
    return cache.GLOBAL_FILE_TREE_CACHE_PUBLIC


@router.get("/api/search/benchmark")
async def api_search_benchmark(request: Request):
    """旧方式と新方式の検索パフォーマンスを比較（localhost限定）"""
    if not is_admin_request(request):
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
