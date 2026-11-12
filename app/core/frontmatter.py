"""ノートの frontmatter（先頭の --- で囲んだ YAML）を読む（Q-13）

索引作り（indexing）とリンクの描画（wikilinks）の両方が使う。前は indexing にあり、wikilinks が indexing を読み込むので、
indexing からは wikilinks を関数の中で読み込んで循環を避けていた。どちらも読み込むだけの小さなモジュールに分けた
"""
import re

import yaml


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """先頭の frontmatter を読み、(frontmatter の辞書, 本文) を返す。無い・YAML が読めないときは ({}, 元の本文)
    （先頭の BOM は外し、改行は LF にそろえる）"""
    frontmatter = {}
    body = content
    if content.startswith('\ufeff'):
        content = content[1:]
        body = content

    content_normalized = content.replace('\r\n', '\n')

    if content_normalized.strip().startswith("---"):
        match = re.match(r'^\s*---\s*\n(.*?)\n---(?:\s*\n|$)', content_normalized, re.DOTALL)
        if match:
            yaml_content = match.group(1)
            try:
                frontmatter = yaml.safe_load(yaml_content) or {}
                body = content_normalized[match.end():]
            except Exception:
                pass
    return frontmatter, body


def is_published(frontmatter: dict) -> bool:
    """frontmatterのpublishフィールドがTrueかどうかを判定します。"""
    publish_state = frontmatter.get('publish')
    return publish_state is True or str(publish_state).lower() == 'true'
