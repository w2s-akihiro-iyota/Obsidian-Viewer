"""Obsidian 記法のリンク・埋め込み（[[...]] / ![[...]]）を HTML にする"""
import re
import uuid
from dataclasses import dataclass, field
from html import escape
from typing import Callable

from app import cache
from app.config import CONTENT_DIR, MAX_EMBED_DEPTH
from app.core.indexing import is_published, parse_frontmatter, resolve_note_path
from app.core.markdown import heading_anchor
from app.services.images import find_image_in_static, image_html, is_image_name

_WIKILINK_RE = re.compile(r'(!?)\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')
_FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})')
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


def _extract_section(body: str, heading: str) -> str | None:
    """見出しから、同じか上位の見出しの手前までを取り出す。見つからなければ None"""
    target = heading_anchor(heading)
    lines = body.split('\n')
    start, level, in_fence = None, 0, False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
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
        is_embed = match.group(1) == '!'
        target = match.group(2).strip()
        alias = match.group(3)
        name, _, heading = (part.strip() for part in target.partition('#'))

        # 画像（| の後ろは表示サイズ）
        if is_embed and name and not heading:
            image_url = find_image_in_static(name)
            if image_url:
                return image_html(image_url, name, alias)
            if is_image_name(name):
                return f'<span class="internal-link-broken">{escape(name)}</span>'

        # 同じノート内の見出しへのリンク
        if not name and heading:
            return f'<a href="#{heading_anchor(heading)}" class="internal-link">{escape(alias or heading)}</a>'

        title = escape(alias or (f"{name} > {heading}" if heading else name))
        path = resolve_note_path(name, cache.FILE_NAME_CACHE, cache.PATH_TO_SLUG)
        if path and published_paths is not None and path not in published_paths:
            path = None
        if path is None:
            return f'<span class="internal-link-broken">{title}</span>'

        href = f"/view/{cache.PATH_TO_SLUG.get(path, path)}"
        if heading:
            href += f"#{heading_anchor(heading)}"

        # 埋め込み。ループ・深すぎる入れ子はリンクにとどめる
        if is_embed and path not in ctx.stack and ctx.depth < MAX_EMBED_DEPTH:
            return ctx.stash(_render_embed(path, heading, href, title, ctx))

        # アイコンはポストプロセス（_inject_note_icons）で付与
        return f'<a href="{href}" class="internal-link">{title}</a>'

    def replace_outside_inline_code(line: str) -> str:
        parts, pos = [], 0
        for m in _INLINE_CODE_RE.finditer(line):
            parts.append(_WIKILINK_RE.sub(replace, line[pos:m.start()]))
            parts.append(m.group(0))
            pos = m.end()
        parts.append(_WIKILINK_RE.sub(replace, line[pos:]))
        return ''.join(parts)

    out, in_fence = [], False
    for line in content.split('\n'):
        if _FENCE_RE.match(line.lstrip('> ')):
            in_fence = not in_fence
            out.append(line)
        elif in_fence or '[[' not in line:
            out.append(line)
        else:
            out.append(replace_outside_inline_code(line))
    return '\n'.join(out)
