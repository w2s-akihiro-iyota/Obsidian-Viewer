"""コンテンツレンダリングサービス"""
import re
from app.core.markdown import md, process_admonition_blocks
from app.services.wikilinks import EmbedContext, process_wikilinks

_NOTE_ICON_SVG = '<svg class="internal-link-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 13H8"/><path d="M16 13h-2"/><path d="M10 17H8"/><path d="M16 17h-2"/></svg>'

_INTERNAL_LINK_RE = re.compile(
    r'(<a\s+href="[^"]*"\s+class="internal-link">)(.*?)(</a>)',
    re.DOTALL
)


def _inject_note_icons(html: str) -> str:
    """レンダリング済みHTMLの内部リンクにノートアイコンを挿入"""
    return _INTERNAL_LINK_RE.sub(
        rf'\1{_NOTE_ICON_SVG}\2\3',
        html
    )


def render_markdown(body: str, published_only: bool = True, deps: set | None = None,
                    source_path: str = "") -> str:
    """
    Markdownレンダリングパイプラインを統合実行する

    published_only=True（既定）のときは、Dataview・内部リンク・埋め込みを公開ノートだけに絞る。
    管理者向けに描画するときだけ False を明示する（渡し忘れても非公開ノートが漏れない側に倒す）。
    deps を渡すと、埋め込んだノートのパスを集める（埋め込み元が更新されたらキャッシュを作り直すため）。
    source_path は描画するノート自身のパス。自分自身の埋め込みを止めるのに使う。
    """
    ctx = EmbedContext(published_only=published_only, render=_render, deps=deps,
                       stack=(source_path,) if source_path else ())
    return _render(body, ctx)


def _render(body: str, ctx: EmbedContext) -> str:
    """描画の本体。埋め込み先の本文も、深さを 1 段増やした ctx でここを通る"""
    body = process_admonition_blocks(body)
    body = process_wikilinks(body, ctx)
    html = md.render(body, {"published_only": ctx.published_only})
    html = _inject_note_icons(html)
    # 埋め込みは描画済みの HTML なので、アイコン付与の後に差し戻す（二重に付けない）
    return ctx.restore(html)
