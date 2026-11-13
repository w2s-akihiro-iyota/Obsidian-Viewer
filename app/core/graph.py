"""グラフビューのデータ（F-8）: 全体グラフと、1 つのノートを中心にしたローカルグラフ

グラフ（LinkGraph）は索引の作り直しで、管理者用（全ノート）と外部向け（公開ノートだけ）の 2 つを作ってキャッシュに載せる（Q-15）。
記事ページのつながりの数と /api/graph は、そのキャッシュ（cached_link_graph）を使い、表示のたびに作らない。
外部の人（と管理者の外部表示）には、公開ノートだけを点にしたグラフの中だけで探索する。
こうすると、非公開ノートを経由した先のノートは出ない。
"""
from collections import deque
from dataclasses import dataclass
from functools import cached_property

from app import cache
from app.config import LOCAL_GRAPH_DEPTHS, LOCAL_GRAPH_MAX_NODES


@dataclass(frozen=True)
class LinkGraph:
    """点（ノート）と線（リンク）。線はリンク元 → リンク先の向きで持つ"""
    nodes: dict[str, dict]          # {path: GLOBAL_FILE_CACHE のノート}（GLOBAL_FILE_CACHE の順）
    links: list[tuple[str, str]]    # [(source_path, target_path)]

    @cached_property
    def neighbors(self) -> dict[str, set[str]]:
        """点ごとの、1 歩でつながっている点（リンクの向きは問わない）。初めて使うときに 1 回だけ作る"""
        neighbors: dict[str, set[str]] = {}
        for source, target in self.links:
            neighbors.setdefault(source, set()).add(target)
            neighbors.setdefault(target, set()).add(source)
        return neighbors


_EMPTY_GRAPH = LinkGraph({}, [])


def build_link_graph(files: list[dict], forward_links: dict[str, list[str]], published_only: bool) -> LinkGraph:
    """見せてよいノートだけを点にし、両端が点にあるリンクだけを線にする（索引の作り直しで呼ぶ）"""
    nodes = {f["path"]: f for f in files if not published_only or f.get("published")}
    links = [(source, target)
             for source, targets in forward_links.items() if source in nodes
             for target in targets if target in nodes]
    return LinkGraph(nodes, links)


def cached_link_graph(published_only: bool) -> LinkGraph:
    """索引の作り直しで作ったグラフ（published_only なら公開ノートだけのもの）。まだ作っていなければ空"""
    graph = cache.LINK_GRAPH_PUBLIC if published_only else cache.LINK_GRAPH
    return graph if graph is not None else _EMPTY_GRAPH


def parse_depth(value: str | int | None) -> int:
    """深さの指定を 1 か 2 にする（それ以外は 1）"""
    try:
        depth = int(value)
    except (TypeError, ValueError):
        return LOCAL_GRAPH_DEPTHS[0]
    return depth if depth in LOCAL_GRAPH_DEPTHS else LOCAL_GRAPH_DEPTHS[0]


def resolve_center(graph: LinkGraph, center: str, slug_to_path: dict[str, str]) -> str | None:
    """中心の指定（スラッグかパス）を、グラフの点のパスにする。点に無ければ None"""
    path = slug_to_path.get(center, center)
    return path if path in graph.nodes else None


def distances_from(graph: LinkGraph, center: str, depth: int) -> dict[str, int]:
    """中心から depth 歩以内の点と、その距離（リンクの向きは問わない）"""
    neighbors = graph.neighbors
    distance = {center: 0}
    queue = deque([center])
    while queue:
        path = queue.popleft()
        if distance[path] >= depth:
            continue
        for nxt in neighbors.get(path, ()):
            if nxt not in distance:
                distance[nxt] = distance[path] + 1
                queue.append(nxt)
    return distance


def neighbor_count(graph: LinkGraph, center: str) -> int:
    """中心から 1 歩でつながっている点の数（リンクの向きは問わない。中心が点に無ければ 0）"""
    if center not in graph.nodes:
        return 0
    return len(distances_from(graph, center, 1)) - 1


def local_graph(graph: LinkGraph, center: str, depth: int, max_nodes: int | None = None) -> tuple[LinkGraph, dict[str, int], bool]:
    """
    中心から depth 歩以内の部分グラフ・各点の距離・上限で切ったか

    max_nodes（省略時は LOCAL_GRAPH_MAX_NODES）を超えるときは、中心に近い点から残す。
    同じ距離なら、つながりの多い点・パスの順。
    """
    if max_nodes is None:
        max_nodes = LOCAL_GRAPH_MAX_NODES
    distance = distances_from(graph, center, depth)
    degree: dict[str, int] = {}
    for source, target in graph.links:
        if source in distance and target in distance:
            degree[source] = degree.get(source, 0) + 1
            degree[target] = degree.get(target, 0) + 1

    kept = sorted(distance, key=lambda p: (distance[p], -degree.get(p, 0), p))[:max_nodes]
    kept_set = set(kept)
    sub = LinkGraph(
        nodes={p: graph.nodes[p] for p in kept},
        links=[(s, t) for s, t in graph.links if s in kept_set and t in kept_set],
    )
    return sub, {p: distance[p] for p in kept}, len(distance) > max_nodes


def graph_payload(graph: LinkGraph, path_to_slug: dict[str, str], distance: dict[str, int] | None = None) -> dict:
    """/api/graph の JSON（nodes・links）。ローカルグラフでは点に中心からの距離を付ける"""
    nodes = []
    for path, f in graph.nodes.items():
        node = {
            "id": path,
            "title": f["title"],
            "tags": f.get("tags", []),
            "slug": path_to_slug.get(path, path),
        }
        if distance is not None:
            node["distance"] = distance[path]
        nodes.append(node)
    return {
        "nodes": nodes,
        "links": [{"source": s, "target": t} for s, t in graph.links],
    }
