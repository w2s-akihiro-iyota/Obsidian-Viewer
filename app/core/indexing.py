from pathlib import Path
import re
import yaml
import os
import math
from datetime import datetime, timezone, timedelta
from app.config import CONTENT_DIR, METADATA_CACHE_FILE
from app import cache

def parse_frontmatter(content):
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

def parse_obsidian_date(date_str):
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

def get_all_files(directory: Path, relative_to: Path, use_cache=True):
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
                publish_state = frontmatter.get('publish')
                is_published = False
                if publish_state is True or str(publish_state).lower() == 'true':
                    is_published = True
                
                files_list.append({
                    "name": file,
                    "path": str(rel_path).replace('\\', '/'),
                    "title": title,
                    "mtime": mtime,
                    "updated": mtime.strftime("%Y-%m-%d %H:%M"),
                    "tags": tags,
                    "published": is_published,
                    "frontmatter": frontmatter,
                    "preview": preview
                })
    
    # Sort by mtime descending
    files_list.sort(key=lambda x: x['mtime'], reverse=True)
    return files_list

def get_file_tree(directory: Path, relative_to: Path, published_only: bool = False):
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
                if published_only:
                    publish_state = frontmatter.get('publish')
                    if not (publish_state is True or str(publish_state).lower() == 'true'):
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

def refresh_global_caches():
    # Clear per-file caches on full refresh
    cache.IMAGE_PATH_CACHE = {}
    cache.MARKDOWN_CACHE = {}
    
    # Refresh all files metadata
    cache.GLOBAL_FILE_CACHE = get_all_files(CONTENT_DIR, CONTENT_DIR, use_cache=False)
    # Refresh tree views (Admin: all, Public: published only)
    cache.GLOBAL_FILE_TREE_CACHE = get_file_tree(CONTENT_DIR, CONTENT_DIR, published_only=False)
    cache.GLOBAL_FILE_TREE_CACHE_PUBLIC = get_file_tree(CONTENT_DIR, CONTENT_DIR, published_only=True)
    print(f"Global cache refreshed: {len(cache.GLOBAL_FILE_CACHE)} files indexed.")
