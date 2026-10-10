"""
添付（MEDIA_DIR）を外部の人に見せてよいかの判定（S-5）

外部の人（公開用ポート）には、公開ノート（publish: true）が参照している添付と、アプリ同梱のサンプル
（MEDIA_SAMPLES_DIR_NAME）だけを見せる。許可リストは索引の作り直しで、公開ノートの本文と frontmatter から作る
（refresh_global_caches）。埋め込みの添付の引き方は描画と同じ embed_media_rel を使い、
「描画では出るのに外部では 404」や、その逆が起きないようにする。記事ページの OGP 画像も同じ抽出から選ぶ。
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from app.config import MEDIA_SAMPLES_DIR_NAME
from app.services.images import MEDIA_URL_PREFIX, MediaIndex, media_path_from_url, media_url
from app.services.wikilinks import embed_media_rel, iter_searchable_text, wikilinks_in_text

# ![alt](url) / ![alt](<url> "タイトル") の括弧の中
_MD_IMAGE_RE = re.compile(r'!\[[^\]\n]*\]\(([^)\n]*)\)')
# <img src="url">
_IMG_SRC_RE = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
# frontmatter の画像を wikilink で書いたとき（image: "[[cover.png]]" / "![[cover.png|300]]"）
_FM_WIKILINK_RE = re.compile(r'^!?\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]$')

# frontmatter で OGP 画像を書くキー（先にあるほうを使う）
FRONTMATTER_IMAGE_KEYS = ("image", "thumbnail")


@dataclass(frozen=True)
class ImageRef:
    """本文・frontmatter の画像の参照 1 件。添付なら rel、外部の URL なら url"""
    rel: str | None = None   # MEDIA_DIR からの相対パス（実在する添付）
    url: str | None = None   # http(s):// の URL（添付ではない）

    @property
    def href(self) -> str:
        return media_url(self.rel) if self.rel else self.url


def _markdown_image_url(target: str) -> str:
    """![alt](...) の括弧の中から URL だけを取り出す（<url> や後ろの "タイトル" を外す）"""
    target = target.strip()
    if target.startswith('<'):
        return target[1:].split('>', 1)[0]
    return target.split(None, 1)[0] if target else ""


def media_rel_from_url(url: str, index: MediaIndex) -> str | None:
    """/media/... の URL が指す添付の相対パス（実在するもの）。/media/ でないか、無ければ None"""
    rel = media_path_from_url(url)
    return index.canonical_path(rel) if rel is not None else None


def _url_ref(url: str, index: MediaIndex) -> ImageRef | None:
    """![](url) / <img src> の URL を参照にする。添付・http(s) の URL 以外（相対パスなど）は None"""
    url = url.strip()
    if url.startswith(MEDIA_URL_PREFIX):
        rel = media_rel_from_url(url, index)
        return ImageRef(rel=rel) if rel else None
    if url.startswith(("http://", "https://")):
        return ImageRef(url=url)
    return None


def frontmatter_media_rel(value, index: MediaIndex) -> str | None:
    """
    frontmatter の image / thumbnail が指す添付の相対パス。添付でなければ None

    /media/... の URL ならその添付、http(s):// や / で始まるほかの URL は対象外、
    それ以外は ![[名前]] と同じ引き方で名前として引く（"[[名前]]" "![[名前|300]]" の形と、
    引用符なしの [[名前]]（YAML では入れ子のリストになる）も受け付ける）。
    """
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list) and len(value[0]) == 1:
        value = str(value[0][0])
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    rel = media_rel_from_url(value, index)
    if rel is not None:
        return rel
    if '://' in value or value.startswith('/'):
        return None
    m = _FM_WIKILINK_RE.match(value)
    return index.resolve(m.group(1) if m else value)


def _frontmatter_refs(frontmatter: dict, index: MediaIndex) -> Iterator[ImageRef]:
    """frontmatter の image / thumbnail の参照（キーの順）"""
    for key in FRONTMATTER_IMAGE_KEYS:
        value = frontmatter.get(key)
        rel = frontmatter_media_rel(value, index)
        if rel:
            yield ImageRef(rel=rel)
        elif isinstance(value, str) and value.strip().startswith(("http://", "https://")):
            yield ImageRef(url=value.strip())


def iter_body_image_refs(body: str, index: MediaIndex) -> Iterator[ImageRef]:
    """
    本文の画像の参照を、出てくる順に返す（コードブロック・インラインコードの中は数えない）

    - 埋め込み ![[...]] のうち、描画で画像になるもの（embed_media_rel）
    - ![alt](url) と <img src="url"> のうち、/media/ の添付か http(s) の URL
    """
    for text in iter_searchable_text(body):
        found: list[tuple[int, ImageRef]] = []
        for pos, link in wikilinks_in_text(text):
            rel = embed_media_rel(link, index)
            if rel:
                found.append((pos, ImageRef(rel=rel)))
        for m in _MD_IMAGE_RE.finditer(text):
            ref = _url_ref(_markdown_image_url(m.group(1)), index)
            if ref:
                found.append((m.start(), ref))
        for m in _IMG_SRC_RE.finditer(text):
            ref = _url_ref(m.group(1), index)
            if ref:
                found.append((m.start(), ref))
        for _, ref in sorted(found, key=lambda item: item[0]):
            yield ref


def note_media_refs(frontmatter: dict, body: str, index: MediaIndex) -> set[str]:
    """ノート 1 件が参照している添付の相対パス（本文と frontmatter の image / thumbnail）"""
    refs = list(_frontmatter_refs(frontmatter, index)) + list(iter_body_image_refs(body, index))
    return {ref.rel for ref in refs if ref.rel}


def first_image_href(frontmatter: dict, body: str, index: MediaIndex | None) -> str | None:
    """
    OGP 画像にする最初の参照（/media/... か http(s) の URL）。無ければ None

    frontmatter の image / thumbnail を先に、無ければ本文で最初に出てくる画像を使う。
    抽出は許可リスト（note_media_refs）と同じなので、外部の人に 404 になる画像を選ばない。
    """
    if index is None:
        index = MediaIndex()
    for ref in _frontmatter_refs(frontmatter, index):
        return ref.href
    for ref in iter_body_image_refs(body, index):
        return ref.href
    return None


def collect_public_media(public_notes: Iterable[tuple[dict, str]], index: MediaIndex) -> frozenset[str]:
    """公開ノートの (frontmatter, 本文) から、外部の人に見せてよい添付の相対パスの集合を作る"""
    allowed: set[str] = set()
    for frontmatter, body in public_notes:
        allowed |= note_media_refs(frontmatter, body, index)
    return frozenset(allowed)


def resolve_media_file(media_dir: Path, requested: str) -> tuple[Path, str] | None:
    """
    要求されたパスを、MEDIA_DIR 配下の実在するファイルに解決し (実パス, MEDIA_DIR からの相対パス) を返す。
    外に出るもの・無いものは None

    .. や絶対パス、MEDIA_DIR の外を指すシンボリックリンクは、resolve() した先が MEDIA_DIR の中かで弾く。
    """
    if not requested or '\x00' in requested:
        return None
    root = media_dir.resolve()
    try:
        target = (root / requested).resolve()
    except (OSError, ValueError):
        return None
    if not target.is_relative_to(root) or not target.is_file():
        return None
    return target, target.relative_to(root).as_posix()


def is_public_media(rel_path: str, public_paths: frozenset[str], index: MediaIndex | None) -> bool:
    """
    添付（MEDIA_DIR からの相対パス。resolve() 済みの実在するもの）を外部の人に見せてよいか

    アプリ同梱のサンプルと、公開ノートが参照するもの（public_paths。索引の綴りで入っている）だけ。
    """
    if rel_path.split('/', 1)[0] == MEDIA_SAMPLES_DIR_NAME:
        return True
    if rel_path in public_paths:
        return True
    # ここに来るのは、要求の綴りが索引に無いのにファイルが実在したとき＝大文字小文字を区別しない
    # ファイルシステム（Windows のフォルダをマウントしたとき等）で、大文字小文字だけ違う綴りで要求されたときだけ。
    # 同じ綴りの添付が索引にある（大文字小文字を区別する）なら別のファイルなので、読み替えない。
    if index is None or rel_path in index.paths:
        return False
    return index.by_lower_path.get(rel_path.lower()) in public_paths
