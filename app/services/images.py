"""画像・メディアファイル（Vault の添付）の解決

添付は MEDIA_DIR に置き、/media/<MEDIA_DIR からの相対パス> で配信する（S-5）。
名前から添付を引く表（MediaIndex）は索引の作り直しで 1 回だけ作り、見つからない名前のたびに全走査しない（Q-12）。
"""
import os
import re
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

IMAGE_EXTS = ('png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp')

# 添付の URL の頭
MEDIA_URL_PREFIX = "/media/"

# ![[画像|300]] / ![[画像|300x200]] のサイズ指定
_IMAGE_SIZE_RE = re.compile(r'^\s*(\d+)(?:\s*x\s*(\d+))?\s*$')


def is_image_name(name: str) -> bool:
    """拡張子から画像ファイル名かを判定する"""
    return '.' in name and name.rsplit('.', 1)[-1].lower() in IMAGE_EXTS


@dataclass(frozen=True)
class MediaIndex:
    """
    MEDIA_DIR の添付の索引（相対パスはすべて / 区切り）

    - paths: すべての添付の相対パス
    - by_name: ファイル名 → 相対パス（同名が複数あれば、パスの並びで先のもの）
    - by_lower_name: 小文字のファイル名 → 相対パス（大文字小文字だけ違う名前で書いたとき）
    - by_lower_stem: 小文字の拡張子なしの名前 → 相対パス（![[画像]] のように拡張子を書かないとき）
    - by_lower_path: 小文字の相対パス → 相対パス
    """
    paths: frozenset[str] = frozenset()
    by_name: dict[str, str] = field(default_factory=dict)
    by_lower_name: dict[str, str] = field(default_factory=dict)
    by_lower_stem: dict[str, str] = field(default_factory=dict)
    by_lower_path: dict[str, str] = field(default_factory=dict)

    def canonical_path(self, rel_path: str) -> str | None:
        """相対パスを、実在する添付の相対パスにそろえる（大文字小文字の違いは許す）。無ければ None"""
        rel_path = rel_path.strip().lstrip('/')
        if rel_path in self.paths:
            return rel_path
        return self.by_lower_path.get(rel_path.lower())

    def resolve(self, name: str) -> str | None:
        """
        ![[名前]] の名前から添付の相対パスを引く。無ければ None

        ファイル名で引き、無ければパス指定（![[フォルダ/画像.png]]）として引く。
        拡張子が無い名前は、拡張子を除いた名前が同じものを引く。大文字小文字の違いは許す。
        """
        name = name.strip()
        if not name:
            return None
        rel = self.by_name.get(name) or self.by_lower_name.get(name.lower())
        if rel is None and '/' in name:
            rel = self.canonical_path(name)
        if rel is None and not is_image_name(name):
            rel = self.by_lower_stem.get(name.lower())
        return rel


def build_media_index(media_dir: Path) -> MediaIndex:
    """MEDIA_DIR を 1 回だけ走査して、添付の索引を作る"""
    rel_paths = []
    if media_dir.is_dir():
        for root, dirs, files in os.walk(media_dir):
            dirs.sort()
            for f in sorted(files):
                rel_paths.append((Path(root) / f).relative_to(media_dir).as_posix())

    by_name: dict[str, str] = {}
    by_lower_name: dict[str, str] = {}
    by_lower_stem: dict[str, str] = {}
    by_lower_path: dict[str, str] = {}
    for rel in rel_paths:
        file_name = rel.rsplit('/', 1)[-1]
        by_name.setdefault(file_name, rel)
        by_lower_name.setdefault(file_name.lower(), rel)
        if '.' in file_name:
            by_lower_stem.setdefault(file_name.rsplit('.', 1)[0].lower(), rel)
        by_lower_path.setdefault(rel.lower(), rel)
    return MediaIndex(paths=frozenset(rel_paths), by_name=by_name, by_lower_name=by_lower_name,
                      by_lower_stem=by_lower_stem, by_lower_path=by_lower_path)


def media_url(rel_path: str) -> str:
    """添付の相対パスから配信の URL を作る（# や空白などはエンコードする）"""
    return MEDIA_URL_PREFIX + quote(rel_path, safe='/')


def media_path_from_url(url: str) -> str | None:
    """/media/... の URL から、MEDIA_DIR からの相対パス（デコード後）を取り出す。/media/ でなければ None"""
    path = urlsplit(url.strip()).path
    if not path.startswith(MEDIA_URL_PREFIX):
        return None
    return unquote(path[len(MEDIA_URL_PREFIX):])


def image_html(url: str, name: str, size: str | None) -> str:
    """![[画像|サイズ]] の img タグ。サイズは数字（幅）か「幅x高さ」だけを受け付ける"""
    attrs = ""
    m = _IMAGE_SIZE_RE.match(size or "")
    if m:
        attrs = f'width="{m.group(1)}"' + (f' height="{m.group(2)}"' if m.group(2) else "")
    return f'<img src="{escape(url)}" alt="{escape(name)}" {attrs} class="obsidian-image">'
