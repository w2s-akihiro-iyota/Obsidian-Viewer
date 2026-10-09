"""画像・メディアファイルの解決"""
import os
import re
from html import escape
from pathlib import Path
from app.config import STATICS_DIR
from app import cache

IMAGE_EXTS = ('png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp')

# ![[画像|300]] / ![[画像|300x200]] のサイズ指定
_IMAGE_SIZE_RE = re.compile(r'^\s*(\d+)(?:\s*x\s*(\d+))?\s*$')


def is_image_name(name: str) -> bool:
    """拡張子から画像ファイル名かを判定する"""
    return '.' in name and name.rsplit('.', 1)[-1].lower() in IMAGE_EXTS


def find_image_in_static(filename: str) -> str | None:
    if filename in cache.IMAGE_PATH_CACHE:
        return cache.IMAGE_PATH_CACHE[filename]

    # Check if filename has extension
    has_ext = is_image_name(filename)

    for root, dirs, files in os.walk(STATICS_DIR):
        # Precise match
        if filename in files:
            full_path = Path(root) / filename
            rel_path = full_path.relative_to(STATICS_DIR)
            rel_path_str = str(rel_path).replace('\\', '/')
            url = f"/static/{rel_path_str}"
            cache.IMAGE_PATH_CACHE[filename] = url
            return url

        # Ambiguous match (if no extension provided in link)
        if not has_ext:
            for f in files:
                if f.lower().startswith(filename.lower() + '.'):
                    full_path = Path(root) / f
                    rel_path = full_path.relative_to(STATICS_DIR)
                    rel_path_str = str(rel_path).replace('\\', '/')
                    url = f"/static/{rel_path_str}"
                    cache.IMAGE_PATH_CACHE[filename] = url
                    return url

    return None


def image_html(url: str, name: str, size: str | None) -> str:
    """![[画像|サイズ]] の img タグ。サイズは数字（幅）か「幅x高さ」だけを受け付ける"""
    attrs = ""
    m = _IMAGE_SIZE_RE.match(size or "")
    if m:
        attrs = f'width="{m.group(1)}"' + (f' height="{m.group(2)}"' if m.group(2) else "")
    return f'<img src="{escape(url)}" alt="{escape(name)}" {attrs} class="obsidian-image">'
