from pathlib import Path
import math
import re
import yaml
import os
import logging

from datetime import datetime, timezone, timedelta
from app.config import CONTENT_DIR, READING_SPEED_JP
from app import cache

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

def get_all_files(directory: Path, relative_to: Path) -> list[dict]:
    files_list = []
    
    # Simple recursive walk
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.md'):
                full_path = Path(root) / file
                rel_path = full_path.relative_to(relative_to)
                
                mtime = datetime.fromtimestamp(full_path.stat().st_mtime)
                
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                
                frontmatter, body = parse_frontmatter(content)
                
                # Create preview (plain text, first 200 chars)
                preview = re.sub(r'<[^>]+>', '', body) # strip HTML if any
                preview = preview.replace('\n', ' ').strip()[:200]
                
                title = frontmatter.get('title') or rel_path.stem
                tags = frontmatter.get('tags')
                if tags is None:
                    tags = []
                elif isinstance(tags, str):
                    tags = [tags]
                
                # Cleanup tags: remove leading '#' and whitespace
                tags = [t.strip().lstrip('#') for t in tags if t and str(t).strip()]
                
                # Check Visibility
                published = is_published(frontmatter)

                # マークアップ除去したプレーンテキスト（全文検索・読了時間用）
                body_text = re.sub(r'<[^>]+>', '', body)
                body_text = re.sub(r'!\[.*?\]\(.*?\)', '', body_text)
                body_text = re.sub(r'\[([^\]]*)\]\(.*?\)', r'\1', body_text)
                body_text = re.sub(r'[#*_~`>\-\|]', '', body_text)
                body_text = body_text.strip()

                # 読了時間の算出
                char_count = len(body_text)
                reading_time = max(1, math.ceil(char_count / READING_SPEED_JP))

                files_list.append({
                    "name": file,
                    "path": str(rel_path).replace('\\', '/'),
                    "title": title,
                    "mtime": mtime,
                    "updated": mtime.strftime("%Y-%m-%d %H:%M"),
                    "tags": tags,
                    "published": published,
                    "frontmatter": frontmatter,
                    "preview": preview,
                    "body_text": body_text,
                    "char_count": char_count,
                    "reading_time": reading_time
                })
    
    # Sort by mtime descending
    files_list.sort(key=lambda x: x['mtime'], reverse=True)
    return files_list

def get_file_tree(directory: Path, relative_to: Path, published_only: bool = False) -> list[dict]:
    tree = []
    
    # Helper to find or create folder in tree
    def get_folder(parent_list, folder_name):
        for item in parent_list:
            if item['type'] == 'directory' and item['name'] == folder_name:
                return item
        new_folder = {"name": folder_name, "type": "directory", "children": []}
        parent_list.append(new_folder)
        return new_folder

    for root, dirs, files in os.walk(directory):
        rel_root = Path(root).relative_to(relative_to)
        
        # Build path to this folder in our tree
        current_level = tree
        if str(rel_root) != '.':
            parts = rel_root.parts
            for part in parts:
                folder = get_folder(current_level, part)
                current_level = folder['children']
        
        for file in files:
            if file.endswith('.md'):
                full_path = Path(root) / file
                rel_path = full_path.relative_to(relative_to)
                
                # Check metadata for title/published
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                
                frontmatter, _ = parse_frontmatter(content)
                
                # Filter if published_only
                if published_only and not is_published(frontmatter):
                    continue

                title = frontmatter.get('title') or rel_path.stem
                current_level.append({
                    "name": file,
                    "title": title,
                    "path": str(rel_path).replace('\\', '/'),
                    "type": "file"
                })

    # Sort tree (folders first, then alphabetical)
    def sort_tree(node_list):
        node_list.sort(key=lambda x: (0 if x['type'] == 'directory' else 1, x['title'].lower() if 'title' in x else x['name'].lower()))
        for item in node_list:
            if item['type'] == 'directory':
                sort_tree(item['children'])
    
    sort_tree(tree)
    return tree

def _build_backlink_cache() -> None:
    """全ファイルの[[wikilink]]を解析し、バックリンクとフォワードリンクのキャッシュを構築"""
    backlinks = {}   # {target_path: [{title, path}]}
    forward = {}     # {source_path: [target_path]}
    wikilink_re = re.compile(r'\[\[([^\]\|#]+)')

    for f in cache.GLOBAL_FILE_CACHE:
        source_path = f["path"]
        source_title = f["title"]

        # ファイルを読み込んでwikilinkを抽出
        full_path = CONTENT_DIR / source_path
        if not full_path.exists():
            continue

        try:
            with open(full_path, 'r', encoding='utf-8', errors='replace') as fh:
                content = fh.read()
        except Exception:
            continue

        _, body = parse_frontmatter(content)
        links = wikilink_re.findall(body)
        resolved_targets = []

        for link_name in links:
            link_name = link_name.strip()
            # FILE_NAME_CACHEで解決
            target_path = cache.FILE_NAME_CACHE.get(link_name)
            if target_path and target_path != source_path:
                resolved_targets.append(target_path)
                # バックリンクに追加
                if target_path not in backlinks:
                    backlinks[target_path] = []
                # 重複チェック
                if not any(bl["path"] == source_path for bl in backlinks[target_path]):
                    backlinks[target_path].append({
                        "title": source_title,
                        "path": source_path
                    })

        forward[source_path] = list(set(resolved_targets))

    cache.BACKLINK_CACHE = backlinks
    cache.FORWARD_LINK_CACHE = forward
    logger.info("Backlink cache built: %d files with backlinks.", len(backlinks))


def refresh_global_caches() -> None:
    # Clear per-file caches on full refresh
    cache.IMAGE_PATH_CACHE = {}
    cache.MARKDOWN_CACHE = {}
    
    # Refresh all files metadata
    cache.GLOBAL_FILE_CACHE = get_all_files(CONTENT_DIR, CONTENT_DIR)
    # Refresh tree views (Admin: all, Public: published only)
    cache.GLOBAL_FILE_TREE_CACHE = get_file_tree(CONTENT_DIR, CONTENT_DIR, published_only=False)
    cache.GLOBAL_FILE_TREE_CACHE_PUBLIC = get_file_tree(CONTENT_DIR, CONTENT_DIR, published_only=True)

    # ファイル名(stem) → パスの逆引きマッピングを構築
    cache.FILE_NAME_CACHE = {}
    for f in cache.GLOBAL_FILE_CACHE:
        stem = Path(f["name"]).stem
        # 同名ファイルが複数ある場合は最初のものを優先（Obsidianの最短パス解決に近い動作）
        if stem not in cache.FILE_NAME_CACHE:
            cache.FILE_NAME_CACHE[stem] = f["path"]

    # バックリンクキャッシュの構築
    _build_backlink_cache()

    logger.info("Global cache refreshed: %d files indexed.", len(cache.GLOBAL_FILE_CACHE))
