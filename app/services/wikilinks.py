"""Obsidian 記法のリンク・埋め込み（[[...]] / ![[...]]）を HTML にする"""
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from html import escape
from typing import Callable, Iterator

from app import cache
from app.config import CONTENT_DIR, MAX_EMBED_DEPTH
from app.core.indexing import is_published, parse_frontmatter, resolve_note_path
from app.core.markdown import heading_anchor
from app.services.images import MediaIndex, image_html, is_image_name, media_url

_WIKILINK_RE = re.compile(r'(!?)\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')
_FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})(.*)$')
_INLINE_CODE_RE = re.compile(r'`[^`\n]+`')
_HEADING_LINE_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')


@dataclass
class EmbedContext:
    """
    1回の描画で共有する情報

    - 埋め込み HTML の退避（Markdown 変換で崩れないよう目印に置き換え、変換後に差し戻す）
    - 埋め込みの入れ子の深さとループ検出
    - 埋め込んだノートの記録（キャッシュの作り直し判定用）
    """
    published_only: bool
    render: Callable[[str, "EmbedContext"], str]   # 埋め込み先の本文を描画する関数（render_markdown の本体）
    deps: set | None = None                 # 埋め込んだノートのパスを集める
    stack: tuple[str, ...] = ()             # 描画中のノートと、いま埋め込み中のノート（ループ検出）
    depth: int = 0                          # 埋め込みの入れ子の深さ（ページ本体は 0）
    _stash: list[str] = field(default_factory=list)
    # 本文に偶然現れない目印にするため、描画ごとに乱数を混ぜる
    _token: str = field(default_factory=lambda: f"OVEMBED{uuid.uuid4().hex[:12]}N")

    def child(self, path: str) -> "EmbedContext":
        """path を埋め込むときの、1段深い描画の情報"""
        return EmbedContext(published_only=self.published_only, render=self.render, deps=self.deps,
                            stack=self.stack + (path,), depth=self.depth + 1)

    def stash(self, html: str) -> str:
        self._stash.append(html)
        return f"{self._token}{len(self._stash) - 1}X"

    def restore(self, html: str) -> str:
        for i, stashed in enumerate(self._stash):
            mark = f"{self._token}{i}X"
            html = html.replace(f"<p>{mark}</p>", stashed).replace(mark, stashed)
        return html


@dataclass(frozen=True)
class WikiLink:
    """本文中の [[...]] / ![[...]] 1 つ分"""
    is_embed: bool          # ![[...]] なら True
    name: str               # リンク先の名前（# より前。[[#見出し]] なら空）
    heading: str            # # より後ろの見出し（無ければ空）
    alias: str | None       # | より後ろ（ノートなら表示名、画像なら表示サイズ）

    @classmethod
    def from_match(cls, m: re.Match) -> "WikiLink":
        name, _, heading = (part.strip() for part in m.group(2).strip().partition('#'))
        return cls(is_embed=m.group(1) == '!', name=name, heading=heading, alias=m.group(3))


class _FenceTracker:
    """
    コードブロック（``` / ~~~）の中かどうかを 1 行ずつ追う

    閉じる行は、開いた記号と同じ種類・同じ長さ以上で、後ろに何も書いていない行だけ（CommonMark と同じ）。
    ```ad-success のように後ろに文字がある行は閉じる行にしない。Admonition の入れ子で数え方がずれないため。
    """

    def __init__(self):
        self._open: tuple[str, int] | None = None   # (記号, 長さ)
        self._info = ""                             # 最後に開いたコードブロックの種類（```dataview なら dataview）

    @property
    def is_open(self) -> bool:
        return self._open is not None

    @property
    def info(self) -> str:
        return self._info

    def in_code(self, line: str) -> bool:
        """この行がコードブロックの区切りか中身なら True"""
        m = _FENCE_RE.match(line)
        if self._open is None:
            if m:
                self._open = (m.group(1)[0], len(m.group(1)))
                self._info = m.group(2).strip()
                return True
            return False
        if m and m.group(1)[0] == self._open[0] and len(m.group(1)) >= self._open[1] and not m.group(2).strip():
            self._open = None
        return True


class _LineRole(Enum):
    """コードブロックから見た行の役割"""
    TEXT = auto()    # コードブロックの外
    OPEN = auto()    # 開く区切り行
    BODY = auto()    # コードブロックの中身
    CLOSE = auto()   # 閉じる区切り行


def _unquote(line: str) -> str:
    """コールアウト（> [!note]）の行頭の > を外す。コールアウトの中のコードブロックも同じように扱うため"""
    return line.lstrip('> ')


def _walk_lines(content: str) -> Iterator[tuple[str, str, _LineRole, str]]:
    """
    本文を 1 行ずつ (元の行, > を外した行, 役割, コードブロックの種類) で返す

    コードブロックの判定はここ 1 か所で行い、リンクの走査（_link_segments）と
    コードブロックの取り出し（iter_fenced_blocks）が共有する。
    """
    fence = _FenceTracker()
    for line in content.split('\n'):
        unquoted = _unquote(line)
        was_open = fence.is_open
        if not fence.in_code(unquoted):
            role = _LineRole.TEXT
        elif not was_open:
            role = _LineRole.OPEN
        elif fence.is_open:
            role = _LineRole.BODY
        else:
            role = _LineRole.CLOSE
        yield line, unquoted, role, fence.info


def _link_segments(content: str, marker: str = '[[') -> Iterator[tuple[str, bool]]:
    """
    本文を「リンクを探す部分」と「探さない部分」に分けて順に返す（つなげると元の本文に戻る）

    探さないのは、コードブロック（コールアウトの中も含む）・インラインコード・行の区切り。
    描画（process_wikilinks）とリンクの走査（iter_wikilinks）が同じ判定を使うための共通部分。
    marker を含まない行は探さない（速くするため。空文字ならすべての行を探す）。
    """
    for i, (line, _, role, _) in enumerate(_walk_lines(content)):
        if i:
            yield '\n', False
        if role is not _LineRole.TEXT or marker not in line:
            yield line, False
            continue
        pos = 0
        for m in _INLINE_CODE_RE.finditer(line):
            yield line[pos:m.start()], True
            yield m.group(0), False
            pos = m.end()
        yield line[pos:], True


def iter_wikilinks(content: str) -> Iterator[WikiLink]:
    """コードの中を飛ばしながら、本文の [[...]] / ![[...]] を出てくる順に返す"""
    for text, searchable in _link_segments(content):
        if searchable:
            for m in _WIKILINK_RE.finditer(text):
                yield WikiLink.from_match(m)


def iter_searchable_text(content: str) -> Iterator[str]:
    """コードブロックとインラインコードを除いた本文を、出てくる順に切れ目ごとに返す（添付の参照を拾う用）"""
    for text, searchable in _link_segments(content, marker=''):
        if searchable:
            yield text


def wikilinks_in_text(text: str) -> Iterator[tuple[int, WikiLink]]:
    """コードを除いた文字列から、[[...]] / ![[...]] を (位置, リンク) で返す"""
    for m in _WIKILINK_RE.finditer(text):
        yield m.start(), WikiLink.from_match(m)


def iter_fenced_blocks(content: str) -> Iterator[tuple[str, str]]:
    """
    コードブロックごとに (種類, 中身) を返す（```dataview なら ("dataview", クエリ)）

    コードブロックの中に書いた ``` は中身として扱う（_walk_lines と同じ判定）。
    """
    lines: list[str] | None = None   # 開いているコードブロックの中身（開いていなければ None）
    info = ""
    for _, unquoted, role, block_info in _walk_lines(content):
        if role is _LineRole.OPEN:
            lines, info = [], block_info
        elif role is _LineRole.BODY:
            lines.append(unquoted)
        elif role is _LineRole.CLOSE:
            yield info, '\n'.join(lines)
            lines = None
    # 閉じずに終わったコードブロックは、Markdown と同じく本文の最後までをコードとして扱う
    if lines is not None:
        yield info, '\n'.join(lines)


class LinkKind(Enum):
    """リンク 1 件の振り分け（描画と公開チェックで共通）"""
    IMAGE = auto()           # 見つかった画像（![[画像]]）
    MISSING_IMAGE = auto()   # 見つからない画像（![[画像.png]] で、画像ファイルが無い）
    HEADING = auto()         # 同じノート内の見出し（[[#見出し]]）
    MISSING_NOTE = auto()    # 存在しないノート（[[画像.png]] のように埋め込みでない画像名も、描画どおりここ）
    PRIVATE_NOTE = auto()    # 非公開ノート（published_paths を渡したときだけ）
    NOTE = auto()            # 表示できるノート


@dataclass(frozen=True)
class LinkTarget:
    """リンクの振り分け結果"""
    kind: LinkKind
    path: str | None = None        # NOTE / PRIVATE_NOTE の解決先（ノートの相対パス）
    image_url: str | None = None   # IMAGE の URL


def embed_media_rel(link: WikiLink, index: MediaIndex | None = None) -> str | None:
    """
    埋め込み 1 件が指す添付の相対パス（MEDIA_DIR から）。添付でなければ None

    添付になるのは見出しの無い埋め込みだけ（| の後ろは表示サイズ）。描画（classify_link）と
    外部に見せる添付の許可リスト（media_access）の両方がこれを使い、引き方を食い違わせない。
    index を省略すると、いまのキャッシュの索引を使う。
    """
    if not (link.is_embed and link.name and not link.heading):
        return None
    index = cache.MEDIA_INDEX if index is None else index
    return index.resolve(link.name) if index is not None else None


def classify_link(link: WikiLink, published_paths: set[str] | None,
                  file_name_map: dict | None = None, path_to_slug: dict | None = None,
                  media_index: MediaIndex | None = None) -> LinkTarget:
    """
    リンク 1 件を、描画で何になるかで振り分ける

    published_paths を渡すと、そこに無いノートを非公開ノートとする（外部向け）。None なら全ノートを表示できる扱い。
    file_name_map / path_to_slug / media_index は名前からノート・添付を引く表。省略時は今のキャッシュを使う
    （索引の作り直しの途中では、差し替える前の新しい表を渡す）。
    """
    rel = embed_media_rel(link, media_index)
    if rel:
        return LinkTarget(LinkKind.IMAGE, image_url=media_url(rel))
    # 見出しの無い画像名の埋め込みで、添付が見つからないもの
    if link.is_embed and not link.heading and is_image_name(link.name):
        return LinkTarget(LinkKind.MISSING_IMAGE)

    if not link.name and link.heading:
        return LinkTarget(LinkKind.HEADING)

    path = resolve_note_path(link.name,
                             cache.FILE_NAME_CACHE if file_name_map is None else file_name_map,
                             cache.PATH_TO_SLUG if path_to_slug is None else path_to_slug)
    if path is None:
        return LinkTarget(LinkKind.MISSING_NOTE)
    if published_paths is not None and path not in published_paths:
        return LinkTarget(LinkKind.PRIVATE_NOTE, path=path)
    return LinkTarget(LinkKind.NOTE, path=path)


def is_missing_note(link: WikiLink, target: LinkTarget) -> bool:
    """
    存在しないノートへのリンクか（公開チェックとダッシュボードの「リンク切れ」で共通の判定）

    [[#]] のように名前も見出しも無いものは、描画でも何も出ないので数えない。
    """
    return target.kind is LinkKind.MISSING_NOTE and bool(link.name)


def _extract_section(body: str, heading: str) -> str | None:
    """見出しから、同じか上位の見出しの手前までを取り出す。見つからなければ None"""
    target = heading_anchor(heading)
    lines = body.split('\n')
    start, level = None, 0
    fence = _FenceTracker()
    for i, line in enumerate(lines):
        if fence.in_code(line):
            continue
        m = _HEADING_LINE_RE.match(line)
        if not m:
            continue
        if start is None:
            if heading_anchor(m.group(2)) == target:
                start, level = i, len(m.group(1))
        elif len(m.group(1)) <= level:
            return '\n'.join(lines[start:i])
    return '\n'.join(lines[start:]) if start is not None else None


def _render_embed(path: str, heading: str, href: str, title: str, ctx: EmbedContext) -> str:
    """ノート（またはその見出しの節）を描画して、埋め込み用の枠で包む"""
    broken = f'<span class="internal-link-broken">{title}</span>'
    try:
        text = (CONTENT_DIR / path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return broken

    frontmatter, body = parse_frontmatter(text)
    # 公開状態は索引ではなく、いま読んだファイルで判定する（再インデックス前に非公開へ変えた場合も漏らさない）
    if ctx.published_only and not is_published(frontmatter):
        return broken
    if ctx.deps is not None:
        ctx.deps.add(path)

    if heading:
        section = _extract_section(body, heading)
        if section is None:
            inner = f'<p class="markdown-embed-missing">見出しが見つかりません: {escape(heading)}</p>'
        else:
            inner = ctx.render(section, ctx.child(path))
    else:
        inner = ctx.render(body, ctx.child(path))

    return (
        '<div class="markdown-embed">'
        f'<div class="markdown-embed-title"><a href="{href}" class="markdown-embed-link">{title}</a></div>'
        f'<div class="markdown-embed-content">{inner}</div>'
        '</div>'
    )


def process_wikilinks(content: str, ctx: EmbedContext) -> str:
    """
    Obsidian 記法を HTML に置き換える

    - ![[画像.png|300]]                 画像
    - [[ノート]] / [[ノート|表示名]]       内部リンク
    - [[ノート#見出し]] / [[#見出し]]      見出しへのリンク
    - [[フォルダ/ノート]]                 パス指定のリンク
    - ![[ノート]] / ![[ノート#見出し]]     ノート（またはその節）の埋め込み

    ctx.published_only のときは、非公開ノートへのリンク・埋め込みをリンク切れと同じ表示にする。
    リンク先のパス（slug）から、非公開ノートの存在やフォルダ構成が外部に見えないようにするため。
    コードブロックとインラインコードの中は置き換えない。
    """
    published_paths = (
        {f["path"] for f in cache.GLOBAL_FILE_CACHE if f.get("published")} if ctx.published_only else None
    )

    def replace(match: re.Match) -> str:
        link = WikiLink.from_match(match)
        name, heading, alias = link.name, link.heading, link.alias
        target = classify_link(link, published_paths)

        if target.kind is LinkKind.IMAGE:
            return image_html(target.image_url, name, alias)
        if target.kind is LinkKind.MISSING_IMAGE:
            return f'<span class="internal-link-broken">{escape(name)}</span>'
        if target.kind is LinkKind.HEADING:
            return f'<a href="#{heading_anchor(heading)}" class="internal-link">{escape(alias or heading)}</a>'

        title = escape(alias or (f"{name} > {heading}" if heading else name))
        # 存在しないノートと、外部向けの非公開ノートは同じ表示にする（非公開ノートの存在を見せない）
        if target.kind is not LinkKind.NOTE:
            return f'<span class="internal-link-broken">{title}</span>'

        path = target.path
        href = f"/view/{cache.PATH_TO_SLUG.get(path, path)}"
        if heading:
            href += f"#{heading_anchor(heading)}"

        # 埋め込み。ループ・深すぎる入れ子はリンクにとどめる
        if link.is_embed and path not in ctx.stack and ctx.depth < MAX_EMBED_DEPTH:
            return ctx.stash(_render_embed(path, heading, href, title, ctx))

        # アイコンはポストプロセス（_inject_note_icons）で付与
        return f'<a href="{href}" class="internal-link">{title}</a>'

    return ''.join(
        _WIKILINK_RE.sub(replace, text) if searchable else text
        for text, searchable in _link_segments(content)
    )
