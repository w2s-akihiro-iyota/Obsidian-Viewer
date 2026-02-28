"""コンテンツレンダリングサービス"""
import re
from app.core.markdown import md, process_admonition_blocks
from app.services.images import process_obsidian_images

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


def render_markdown(body: str) -> str:
    """Markdownレンダリングパイプラインを統合実行する"""
    body = process_admonition_blocks(body)
    body = process_obsidian_images(body)
    html = md.render(body)
    html = _inject_note_icons(html)
    return html
