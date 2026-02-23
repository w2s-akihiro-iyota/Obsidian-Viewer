"""コンテンツレンダリングサービス"""
from app.core.markdown import md, process_admonition_blocks
from app.services.images import process_obsidian_images


def render_markdown(body: str) -> str:
    """Markdownレンダリングパイプラインを統合実行する"""
    body = process_admonition_blocks(body)
    body = process_obsidian_images(body)
    return md.render(body)
