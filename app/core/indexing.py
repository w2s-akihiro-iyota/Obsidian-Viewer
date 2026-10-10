from pathlib import Path
import math
import re
import yaml
import os
import logging
import threading

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from app.config import CONTENT_DIR, MEDIA_DIR, READING_SPEED_JP
from app import cache
from app.utils.slug import slugify_path

logger = logging.getLogger("app.indexing")

def parse_frontmatter(content: str) -> tuple[dict, str]:
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

def parse_obsidian_date(date_str: str) -> datetime | None:
    if not date_str: return None
    if isinstance(date_str, (datetime, datetime.date)): return date_str
    
    date_str = str(date_str).strip()
    patterns = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d'
    ]
    for fmt in patterns:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

# 一覧の抜粋の文字数
PREVIEW_LENGTH = 200

# 行頭の記号
_FENCE_LINE_RE = re.compile(r'^[ \t]*(```|~~~).*$', re.MULTILINE)
_CALLOUT_RE = re.compile(r'^(?:[ \t]*>[ \t]*)+\[![^\]\n]*\][+-]?', re.MULTILINE)
_QUOTE_RE = re.compile(r'^(?:[ \t]*>)+[ \t]?', re.MULTILINE)
_HEADING_RE = re.compile(r'^[ \t]*#{1,6}[ \t]+', re.MULTILINE)
_LIST_RE = re.compile(r'^[ \t]*(?:[-*+]|\d+[.)])[ \t]+(?:\[[ xX]\][ \t]+)?', re.MULTILINE)
_HR_RE = re.compile(r'^[ \t]*(?:[-*_][ \t]*){3,}$', re.MULTILINE)
_TABLE_SEP_RE = re.compile(r'^[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$', re.MULTILINE)
# 文中の記号（閉じ忘れで次の行以降を巻き込まないよう、[] () の中は改行をまたがない）
_COMMENT_RE = re.compile(r'<!--.*?-->|%%.*?%%', re.DOTALL)
_EMBED_RE = re.compile(r'!\[\[[^\]\n]*\]\]|!\[[^\]\n]*\]\([^)\n]*\)')
_WIKILINK_ALIAS_RE = re.compile(r'\[\[[^\]|\n]*\|([^\]\n]*)\]\]')
_WIKILINK_RE = re.compile(r'\[\[([^\]\n]*)\]\]')
_LINK_RE = re.compile(r'\[([^\]\n]*)\]\([^)\n]*\)')
_HTML_TAG_RE = re.compile(r'<[^>]+>')
# 強調: ** __ ~~ == と単独の *。_ は英数字に挟まれたもの（snake_case）だけ残す
_EMPHASIS_RE = re.compile(r'\*\*|__|~~|==|\*|(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])')
_SPACES_RE = re.compile(r'\s+')


def make_preview(body: str, limit: int = PREVIEW_LENGTH) -> str:
    """
    一覧のカードに出す抜粋を作る。

    見出し・リスト・引用・強調・コード・リンク・画像・HTML タグ・callout の記法を除いた本文を、
    空白をつめて limit 文字で切る。コードフェンスは ``` の行だけを除き、中身は残す。
    """
    text = body.replace('\r\n', '\n')
    text = _COMMENT_RE.sub('', text)
    text = _FENCE_LINE_RE.sub('', text)

    # 行頭の記号（callout → 引用 → 見出し・リストの順。引用の中のリストも外れる）
    text = _CALLOUT_RE.sub('', text)
    text = _QUOTE_RE.sub('', text)
    text = _HEADING_RE.sub('', text)
    text = _LIST_RE.sub('', text)
    text = _HR_RE.sub('', text)
    text = _TABLE_SEP_RE.sub('', text)

    # 画像は除き、リンクは表示する文字だけにする
    text = _EMBED_RE.sub('', text)
    text = _WIKILINK_ALIAS_RE.sub(r'\1', text)
    text = _WIKILINK_RE.sub(r'\1', text)
    text = _LINK_RE.sub(r'\1', text)
    text = _HTML_TAG_RE.sub('', text)

    text = _EMPHASIS_RE.sub('', text)
    text = text.replace('`', '').replace('|', ' ')
    text = _SPACES_RE.sub(' ', text).strip()
    return text[:limit]


@dataclass(frozen=True)
class NoteRecord:
    """
    索引の作り直しで 1 回だけ読んだノート 1 件（Q-1）

    一覧・ツリー・リンクの表・添付の許可リストは、すべてこれから作る（ノートを何度も読み直さない）。
    本文（body）は作り直しの間だけ使い、キャッシュには載せない。
    """
    rel_path: str           # CONTENT_DIR からの相対パス（/ 区切り）
    name: str               # ファイル名（拡張子つき）
    mtime: datetime
    frontmatter: dict
    body: str               # frontmatter を除いた本文

    @property
    def title(self) -> str:
        # title: 2024 のような数値でも文字列として扱う（検索・並び替えで例外にしない）
        return str(self.frontmatter.get('title') or Path(self.rel_path).stem)

    @property
    def published(self) -> bool:
        return is_published(self.frontmatter)


def scan_notes(directory: Path, relative_to: Path) -> list[NoteRecord]:
    """directory 配下の .md を 1 回ずつ読み、frontmatter と本文に分けて返す"""
    notes = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if not file.endswith('.md'):
                continue
            full_path = Path(root) / file
            rel_path = full_path.relative_to(relative_to)
            mtime = datetime.fromtimestamp(full_path.stat().st_mtime)
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            frontmatter, body = parse_frontmatter(content)
            notes.append(NoteRecord(rel_path=rel_path.as_posix(), name=file, mtime=mtime,
                                    frontmatter=frontmatter, body=body))
    return notes


def _file_entry(note: NoteRecord) -> dict:
    """一覧（GLOBAL_FILE_CACHE）の 1 件"""
    tags = note.frontmatter.get('tags')
    if tags is None:
        tags = []
    elif isinstance(tags, str):
        tags = [tags]
    # Cleanup tags: remove leading '#' and whitespace
    tags = [t.strip().lstrip('#') for t in tags if t and str(t).strip()]

    # マークアップ除去したプレーンテキスト（全文検索・読了時間用）
    body_text = re.sub(r'<[^>]+>', '', note.body)
    body_text = re.sub(r'!\[.*?\]\(.*?\)', '', body_text)
    body_text = re.sub(r'\[([^\]]*)\]\(.*?\)', r'\1', body_text)
    body_text = re.sub(r'[#*_~`>\-\|]', '', body_text)
    body_text = body_text.strip()

    # 読了時間の算出
    char_count = len(body_text)
    reading_time = max(1, math.ceil(char_count / READING_SPEED_JP))

    return {
        "name": note.name,
        "path": note.rel_path,
        "title": note.title,
        "mtime": note.mtime,
        "updated": note.mtime.strftime("%Y-%m-%d %H:%M"),
        "tags": tags,
        "published": note.published,
        "frontmatter": note.frontmatter,
        # 一覧の抜粋（Markdown の記号を除いた本文）
        "preview": make_preview(note.body),
        "body_text": body_text,
        "char_count": char_count,
        "reading_time": reading_time
    }


def build_file_list(notes: list[NoteRecord]) -> list[dict]:
    """一覧（更新日時の新しい順）を作る"""
    files_list = [_file_entry(n) for n in notes]
    files_list.sort(key=lambda x: x['mtime'], reverse=True)
    return files_list


def build_file_tree(files: list[dict], published_only: bool = False) -> list[dict]:
    """
    一覧の path / name / title / published からファイルツリーを作る

    フォルダはノートを含むものだけ出す（公開用の木に、非公開ノートしか無いフォルダの名前を出さないため）。
    """
    tree = []

    # Helper to find or create folder in tree
    def get_folder(parent_list, folder_name, folder_path):
        for item in parent_list:
            if item['type'] == 'directory' and item['name'] == folder_name:
                return item
        new_folder = {"name": folder_name, "path": folder_path, "type": "directory", "children": []}
        parent_list.append(new_folder)
        return new_folder

    for f in files:
        if published_only and not f["published"]:
            continue
        current_level = tree
        parts = f["path"].split('/')[:-1]
        for i, part in enumerate(parts):
            folder = get_folder(current_level, part, '/'.join(parts[:i + 1]))
            current_level = folder['children']
        current_level.append({
            "name": f["name"],
            "title": f["title"],
            "path": f["path"],
            "type": "file",
            "published": f["published"],
        })

    # Sort tree (folders first, then by file name like Obsidian)
    def sort_tree(node_list):
        node_list.sort(key=lambda x: (0 if x['type'] == 'directory' else 1, x['name'].lower()))
        for item in node_list:
            if item['type'] == 'directory':
                sort_tree(item['children'])

    sort_tree(tree)
    return tree


def get_all_files(directory: Path, relative_to: Path) -> list[dict]:
    """directory 配下のノートの一覧（scan_notes の薄いラッパー。テスト・単発の確認用。索引の作り直しは使わない）"""
    return build_file_list(scan_notes(directory, relative_to))


def get_file_tree(directory: Path, relative_to: Path, published_only: bool = False) -> list[dict]:
    """directory 配下のノートのツリー（scan_notes の薄いラッパー。テスト・単発の確認用。索引の作り直しは使わない）"""
    return build_file_tree(get_all_files(directory, relative_to), published_only)


def resolve_note_path(name: str, file_name_map: dict, path_to_slug: dict) -> str | None:
    """
    [[name]] の name からノートの相対パスを引く（描画側とバックリンク作成側で共通のルール）

    ファイル名（拡張子なし）で引き、無ければパス指定（[[フォルダ/ノート]]）として引く。末尾の .md は無視する。
    """
    lookup = name[:-3] if name.endswith(".md") else name
    path = file_name_map.get(lookup)
    if path is None and f"{lookup}.md" in path_to_slug:
        path = f"{lookup}.md"
    return path


def _build_link_maps(files: list[dict], bodies: dict[str, str], file_name_map: dict, path_to_slug: dict,
                     media_index=None) -> tuple[dict, dict]:
    """
    全ファイルの[[wikilink]]を解析し、(バックリンク, フォワードリンク) のマップを作る

    bodies は {ノートの相対パス: 本文}（scan_notes で読んだもの。ここではファイルを読み直さない）。
    media_index は添付の索引（作り直しの途中の新しいもの。見つからない画像とリンク切れを分けるのに使う）。
    リンクの拾い方（コードの中は数えない・見出しと別名の分け方）は描画と同じ iter_wikilinks を使う。
    埋め込み（![[ノート]]）もリンクとして数える。
    あわせて、存在しないノートへのリンク先の名前を各ノートの "missing_links" に入れる
    （ダッシュボードの「リンク切れ」用。判定は公開チェックと同じ is_missing_note）。
    """
    # wikilinks は indexing を読み込むため、循環しないようここで読み込む
    from app.services.wikilinks import classify_link, is_missing_note, iter_wikilinks

    backlinks = {}   # {target_path: [{title, path}]}
    forward = {}     # {source_path: [target_path]}

    for f in files:
        source_path = f["path"]
        source_title = f["title"]
        body = bodies.get(source_path)
        if body is None:
            continue

        resolved_targets = []
        missing_links: dict[str, None] = {}   # 出てきた順を保ったまま重複を除く

        for link in iter_wikilinks(body):
            if not link.name:   # [[#見出し]] は同じノート内
                continue
            target_path = resolve_note_path(link.name, file_name_map, path_to_slug)
            if target_path is None:
                # 引けなかったリンクだけ、描画と同じ振り分けでリンク切れか（見つからない画像などでないか）を見る
                target = classify_link(link, None, file_name_map, path_to_slug, media_index)
                if is_missing_note(link, target):
                    missing_links.setdefault(link.name)
                continue
            if target_path != source_path:
                resolved_targets.append(target_path)
                # バックリンクに追加
                if target_path not in backlinks:
                    backlinks[target_path] = []
                # 重複チェック
                if not any(bl["path"] == source_path for bl in backlinks[target_path]):
                    backlinks[target_path].append({
                        "title": source_title,
                        "path": source_path,
                        "slug": path_to_slug.get(source_path, source_path)
                    })

        forward[source_path] = list(set(resolved_targets))
        f["missing_links"] = list(missing_links)

    logger.info("Backlink cache built: %d files with backlinks.", len(backlinks))
    return backlinks, forward


# キャッシュの作り直しは同時に 1 本だけ（同期・保存・再インデックスが別スレッドから呼ぶため）
_refresh_lock = threading.Lock()


def refresh_global_caches() -> None:
    """
    全キャッシュを作り直す

    新しい内容はすべてローカル変数で組み立て、最後にまとめて差し替える。
    作り直しの途中で、ほかのリクエストが中途半端な状態（一覧は新しく、スラッグは古い等）を見ないようにするため。
    """
    with _refresh_lock:
        try:
            _refresh_global_caches()
        except Exception:
            # 失敗したら外部に見せる添付の許可リストを空にする（fail-closed）。
            # 古い許可リストが残ると、非公開にしたノートの添付が見え続けるため。次の作り直しで戻る
            cache.PUBLIC_MEDIA_PATHS = frozenset()
            logger.exception("Global cache refresh failed; cleared the public media list.")
            raise


def _refresh_global_caches() -> None:
    # 循環しないようここで読み込む（どちらも wikilinks 経由で indexing を読み込む）
    from app.services.images import build_media_index
    from app.services.media_access import collect_public_media

    # 各ノートを 1 回だけ読み、一覧・ツリー・リンクの表・添付の許可リストを全部ここから作る（Q-1）
    notes = scan_notes(CONTENT_DIR, CONTENT_DIR)
    files = build_file_list(notes)
    # 本文は作り直しの間だけ使う（キャッシュには載せない）
    bodies = {n.rel_path: n.body for n in notes}
    # Refresh tree views (Admin: all, Public: published only)
    tree = build_file_tree(files, published_only=False)
    tree_public = build_file_tree(files, published_only=True)

    # 添付の索引（名前 → MEDIA_DIR からの相対パス）
    media_index = build_media_index(MEDIA_DIR)

    # ファイル名(stem) → パスの逆引きマッピングを構築
    file_name_map = {}
    for f in files:
        stem = Path(f["name"]).stem
        # 同名ファイルが複数ある場合は最初のものを優先（Obsidianの最短パス解決に近い動作）
        if stem not in file_name_map:
            file_name_map[stem] = f["path"]

    # スラッグマッピングの構築
    slug_to_path = {}
    path_to_slug = {}
    for f in files:
        base_slug = slugify_path(f["path"])
        slug = base_slug
        counter = 2
        while slug in slug_to_path:
            slug = f"{base_slug}-{counter}"
            counter += 1
        slug_to_path[slug] = f["path"]
        path_to_slug[f["path"]] = slug
        f["slug"] = slug

    # ファイルツリーにもスラッグを付与
    def _apply_slug_to_tree(nodes):
        for node in nodes:
            if node["type"] == "file":
                node["slug"] = path_to_slug.get(node.get("path", ""), "")
            elif node["type"] == "directory":
                _apply_slug_to_tree(node.get("children", []))
    _apply_slug_to_tree(tree)
    _apply_slug_to_tree(tree_public)

    # バックリンクキャッシュの構築
    backlinks, forward = _build_link_maps(files, bodies, file_name_map, path_to_slug, media_index)

    # 外部の人に見せてよい添付（公開ノートが参照するもの）
    public_media = collect_public_media(
        [(n.frontmatter, n.body) for n in notes if n.published], media_index)

    # TF-IDF検索インデックスの構築
    from app.core.search import SearchIndex
    idx = SearchIndex()
    idx.build(files)

    # ここで一気に差し替える
    cache.MEDIA_INDEX = media_index
    cache.PUBLIC_MEDIA_PATHS = public_media
    cache.MARKDOWN_CACHE = {}
    cache.GLOBAL_FILE_CACHE = files
    cache.GLOBAL_FILE_TREE_CACHE = tree
    cache.GLOBAL_FILE_TREE_CACHE_PUBLIC = tree_public
    cache.FILE_NAME_CACHE = file_name_map
    cache.SLUG_TO_PATH = slug_to_path
    cache.PATH_TO_SLUG = path_to_slug
    cache.BACKLINK_CACHE = backlinks
    cache.FORWARD_LINK_CACHE = forward
    cache.SEARCH_INDEX = idx

    logger.info("Global cache refreshed: %d files indexed, %d media (%d public).",
                len(files), len(media_index.paths), len(public_media))
