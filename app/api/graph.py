"""グラフビュー エンドポイント"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import cache
from app.api import templates
from app.core.graph import build_link_graph, graph_payload, local_graph, parse_depth, resolve_center
from app.utils.helpers import is_admin_request, is_public_view

router = APIRouter()


@router.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    """グラフビューページを表示（?focus=<slug> は JS がそのノートに寄せる）"""
    is_localhost = is_admin_request(request)
    return templates.TemplateResponse(request=request, name="graph.html", context={
        "request": request,
        "is_localhost": is_localhost
    })


@router.get("/api/graph")
async def api_graph(request: Request, center: str = "", depth: str = "",
                    view_as: str = Query("", alias="as")):
    """
    グラフデータ（ノードとリンク）をJSONで返す

    center（スラッグかパス）を付けると、そのノートから depth 歩（1 か 2。ほかは 1）以内のローカルグラフを返す。
    点には中心からの距離（distance）を付ける。中心が見つからない（外部の人に非公開のノートを含む）ときは 404。
    外部の人と、管理者の外部表示（?as=public）には、公開ノートだけで作る。
    """
    published_only = is_public_view(request, view_as)
    graph = build_link_graph(cache.GLOBAL_FILE_CACHE, cache.FORWARD_LINK_CACHE, published_only)

    if not center:
        return JSONResponse(content=graph_payload(graph, cache.PATH_TO_SLUG))

    center_path = resolve_center(graph, center, cache.SLUG_TO_PATH)
    if center_path is None:
        raise HTTPException(status_code=404, detail="Note not found")
    sub, distance, truncated = local_graph(graph, center_path, parse_depth(depth))
    payload = graph_payload(sub, cache.PATH_TO_SLUG, distance)
    payload["center"] = center_path
    payload["truncated"] = truncated
    return JSONResponse(content=payload)
