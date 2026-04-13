"""グラフビュー エンドポイント"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import cache
from app.api import templates
from app.utils.helpers import is_request_local

router = APIRouter()


@router.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    """グラフビューページを表示"""
    is_localhost = is_request_local(request)
    return templates.TemplateResponse(request=request, name="graph.html", context={
        "request": request,
        "is_localhost": is_localhost
    })


@router.get("/api/graph")
async def api_graph(request: Request):
    """グラフデータ（ノードとリンク）をJSONで返す"""
    is_localhost = is_request_local(request)

    # ノード生成
    nodes = []
    node_paths = set()
    for f in cache.GLOBAL_FILE_CACHE:
        if not is_localhost and not f.get("published"):
            continue
        nodes.append({
            "id": f["path"],
            "title": f["title"],
            "tags": f.get("tags", []),
            "slug": cache.PATH_TO_SLUG.get(f["path"], f["path"])
        })
        node_paths.add(f["path"])

    # リンク生成（FORWARD_LINK_CACHEから）
    links = []
    for source, targets in cache.FORWARD_LINK_CACHE.items():
        if source not in node_paths:
            continue
        for target in targets:
            if target in node_paths:
                links.append({
                    "source": source,
                    "target": target
                })

    return JSONResponse(content={"nodes": nodes, "links": links})
