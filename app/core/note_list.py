"""トップのノート一覧（D-2）: 絞り込みの条件・公開状態の絞り込み・並び替え・タグの集計"""
from collections import Counter
from dataclasses import dataclass, replace
from typing import Callable
from urllib.parse import urlencode

# 並び替え（クエリの sort の値 → 表示名と並べ方）。先頭が既定
LIST_SORTS: dict[str, tuple[str, Callable[[list[dict]], list[dict]]]] = {
    "updated": ("更新日（新しい順）", lambda files: sorted(files, key=lambda f: f["mtime"], reverse=True)),
    "updated_asc": ("更新日（古い順）", lambda files: sorted(files, key=lambda f: f["mtime"])),
    "title": ("タイトル順", lambda files: sorted(files, key=lambda f: str(f["title"]).casefold())),
    "chars": ("文字数（多い順）", lambda files: sorted(files, key=lambda f: f.get("char_count", 0), reverse=True)),
}
# 公開状態の絞り込み（管理者だけ）。先頭が既定
LIST_VISIBILITIES: dict[str, str] = {"all": "すべて", "public": "公開", "private": "非公開"}

DEFAULT_SORT = next(iter(LIST_SORTS))
DEFAULT_VISIBILITY = next(iter(LIST_VISIBILITIES))


def count_tags(files: list[dict]) -> Counter:
    """タグごとのノート数（一覧とダッシュボードで共通）"""
    counter: Counter = Counter()
    for f in files:
        for t in (f.get("tags") or []):
            counter[t] += 1
    return counter


def filter_visibility(files: list[dict], visibility: str) -> list[dict]:
    """公開状態で絞る（all はそのまま）"""
    if visibility == "public":
        return [f for f in files if f.get("published")]
    if visibility == "private":
        return [f for f in files if not f.get("published")]
    return list(files)


def sort_files(files: list[dict], sort: str) -> list[dict]:
    return LIST_SORTS[sort][1](files)


@dataclass(frozen=True)
class ListQuery:
    """一覧の条件。既定値の条件は URL に付けない"""
    q: str = ""
    tag: str = ""
    visibility: str = DEFAULT_VISIBILITY
    sort: str = DEFAULT_SORT
    page: int = 1

    @classmethod
    def from_params(cls, q: str, tag: str, visibility: str, sort: str, page: int, is_admin: bool) -> "ListQuery":
        """クエリの値を検証して作る。不正な値は既定に倒す。外部の人は公開状態を選べない"""
        if sort not in LIST_SORTS:
            sort = DEFAULT_SORT
        if not is_admin or visibility not in LIST_VISIBILITIES:
            visibility = DEFAULT_VISIBILITY
        return cls(q=q, tag=tag, visibility=visibility, sort=sort, page=max(page, 1))

    def url(self, **changes) -> str:
        """一部の条件を変えた一覧の URL。ページは指定しなければ 1 に戻す"""
        changes.setdefault("page", 1)
        changed = replace(self, **changes)
        default = ListQuery()
        params = {k: getattr(changed, k) for k in ("q", "tag", "visibility", "sort", "page")
                  if getattr(changed, k) != getattr(default, k)}
        query = urlencode(params)
        return "/?" + query if query else "/"

    def active_filters(self) -> list[dict]:
        """効いている条件（件数の横のチップ。url はその条件だけを外した一覧）"""
        filters = []
        if self.visibility != DEFAULT_VISIBILITY:
            label = LIST_VISIBILITIES[self.visibility]
            filters.append({"label": label, "url": self.url(visibility=DEFAULT_VISIBILITY),
                            "remove_label": f"公開状態「{label}」の絞り込みを外す"})
        if self.tag:
            filters.append({"label": f"#{self.tag}", "url": self.url(tag=""),
                            "remove_label": f"タグ「{self.tag}」の絞り込みを外す"})
        if self.q:
            filters.append({"label": f"“{self.q}”", "url": self.url(q=""),
                            "remove_label": f"検索語「{self.q}」を外す"})
        return filters

    def clear_url(self) -> str:
        """条件をすべて外した一覧の URL（並び替えは残す）"""
        return self.url(q="", tag="", visibility=DEFAULT_VISIBILITY)


@dataclass(frozen=True)
class NoteList:
    """一覧の画面に出すもの"""
    files: list[dict]                   # 絞り込み・並び替え後の全件
    visible_total: int                  # 閲覧者に見えるノートの総数
    visibility_counts: dict[str, int]   # 公開状態ごとの件数（検索語・タグで絞った後）
    tag_counts: dict[str, int]          # タグ → 件数（件数の多い順、同数は名前順）
    top_tags: list[str]                 # 上の列に出すタグ
    all_tags: list[str]                 # 全タグ（名前順）

    @property
    def hidden_tag_count(self) -> int:
        """上の列に出ていないタグの数（「＋ほか N」）"""
        return len(set(self.all_tags) - set(self.top_tags))


def build_note_list(all_files: list[dict], query: ListQuery, is_admin: bool, top_tag_count: int) -> NoteList:
    """
    条件で一覧を作る。

    外部の人には公開ノートだけを見せ、タグの一覧と件数も公開ノートだけで数える（非公開ノートのタグを漏らさない）。
    """
    visible = all_files if is_admin else filter_visibility(all_files, "public")

    matched = visible
    if query.q:
        q_lower = query.q.lower()
        matched = [f for f in matched if q_lower in str(f["title"]).lower() or q_lower in f["path"].lower()]
    if query.tag:
        matched = [f for f in matched if query.tag in (f.get("tags") or [])]
    visibility_counts = {v: len(filter_visibility(matched, v)) for v in LIST_VISIBILITIES}

    files = filter_visibility(matched, query.visibility)
    # 検索中は今までどおり（キャッシュの順＝更新日の新しい順）。並び替えは検索語が無いときだけ
    if not query.q:
        files = sort_files(files, query.sort)

    # タグの件数は、公開状態で絞った一覧で数える（検索語・選択中のタグには左右されない）
    counter = count_tags(filter_visibility(visible, query.visibility))
    tag_counts = dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))
    top_tags = list(tag_counts)[:top_tag_count]
    # 選択中のタグが上位に無くても、選択中だと分かるように上の列に出す
    if query.tag and query.tag not in top_tags:
        top_tags.append(query.tag)

    return NoteList(files=files, visible_total=len(visible), visibility_counts=visibility_counts,
                    tag_counts=tag_counts, top_tags=top_tags, all_tags=sorted(tag_counts))
