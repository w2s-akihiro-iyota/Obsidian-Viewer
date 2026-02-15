from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import markdown_it
from markdown_it.tree import SyntaxTreeNode
import os
from datetime import datetime, timezone, timedelta
import yaml
import re
import math
from urllib.parse import quote
import json

app = FastAPI(title="Obsidian Viewer")

# Configuration
BASE_DIR = Path(__file__).resolve().parent
CONTENT_DIR = BASE_DIR / "content"
if not CONTENT_DIR.exists():
    CONTENT_DIR.mkdir()

METADATA_CACHE_FILE = BASE_DIR / "metadata_cache.json"

# Static Files
STATICS_DIR = BASE_DIR / "static"
if not STATICS_DIR.exists():
    STATICS_DIR.mkdir()
app.mount("/static", StaticFiles(directory=str(STATICS_DIR)), name="static")

# Templates
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["timestamp"] = int(datetime.now().timestamp())

# Markdown Setup
def mark_plugin(md):
    def mark(state, silent):
        start = state.pos
        marker = '=='
        if state.src[start:start+2] != marker: return False
        found = False
        pos = start + 2
        while pos < state.posMax - 1:
            if state.src[pos:pos+2] == marker:
                found = True
                break
            pos += 1
        if not found: return False
        if silent: return True
        state.pos = start + 2
        state.push('mark_open', 'mark', 1)
        token = state.push('text', '', 0)
        token.content = state.src[start+2:pos]
        state.push('mark_close', 'mark', -1)
        state.pos = pos + 2
        return True
    md.inline.ruler.before('emphasis', 'mark', mark)

md = (
    markdown_it.MarkdownIt("commonmark", {"breaks": True, "html": True})
    .enable("table")
    .enable("strikethrough")
    .use(mark_plugin)
)

# Custom fence renderer to ensure compatibility with highlight.js
def render_fence(tokens, idx, options, env):
    token = tokens[idx]
    info = token.info.strip() if token.info else ""
    lang = info.split()[0] if info else ""
    
    # If the info is "cardlink", let the other renderer handle it (or handle it here if it was the main one)
    # But wait, we are replacing the default renderer usage.
    # The existing code registers `render_cardlink` which calls `default_fence_renderer`.
    # So we should monkeypatch `default_fence_renderer` or just rely on `markdown-it` default.
    
    # Markdown-it default produces <pre><code class="language-xyz">
    # Highlight.js works with this.
    # But maybe we need to add "hljs" class explicitly to avoid FOUC or detection issues?
    
    return markdown_it.renderer.RendererHTML.fence(md.renderer, tokens, idx, options, env)

# We are using render_cardlink as the main fence rule. 
# It delegates to default_fence_renderer.
# Let's check render_cardlink again.
default_fence_renderer = md.renderer.rules.get("fence", markdown_it.renderer.RendererHTML.fence)

def render_cardlink(tokens, idx, options, env):
    token = tokens[idx]
    info = token.info.strip()
    if info == 'cardlink':
        try:
            data = yaml.safe_load(token.content)
            if isinstance(data, list): data = data[0]
            if not isinstance(data, dict): raise ValueError("Invalid data format")
            html = f"""
            <a href="{data.get('url', '#')}" class="link-card" target="_blank">
                <div class="link-card-content">
                    <div class="link-card-title">{data.get('title', '')}</div>
                    <div class="link-card-description">{data.get('description', '')}</div>
                    <div class="link-card-meta">
                        <img src="{data.get('favicon', '')}" class="link-card-favicon" onerror="this.style.display='none'">
                        <span class="link-card-host">{data.get('host', '')}</span>
                    </div>
                </div>
                <div class="link-card-image" style="background-image: url('{data.get('image', '')}')"></div>
            </a>
            """
            return html
        except Exception: pass
    return default_fence_renderer(tokens, idx, options, env)

md.renderer.rules["fence"] = render_cardlink

from markdown_it.token import Token

# Icons mapping (SVG content)
CALLOUT_ICONS = {
    "note": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-pencil"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>""",
    "tip": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-lightbulb"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-1.5 1.5-3 1.5-5 0-4-3.5-7-8-7s-8 3-8 7c0 2 .5 3.5 1.5 5 .8.8 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg>""",
    "warning": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-triangle-alert"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>""",
    "danger": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-flame"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.1.243-2.188.7-3.128a5.41 5.41 0 0 1 2.8 2.628Z"/></svg>""",
    "error": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-x-octagon"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>""",
    "success": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check"><path d="M20 6 9 17l-5-5"/></svg>""",
    "info": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-info"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>""",
    "important": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-lightbulb"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-1.5 1.5-3 1.5-5 0-4-3.5-7-8-7s-8 3-8 7c0 2 .5 3.5 1.5 5 .8.8 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg>""",
    "question": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-help-circle"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>"""
}

def obsidian_callouts(state):
    tokens = state.tokens
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.type == 'blockquote_open':
            if i + 2 < len(tokens):
                t1 = tokens[i+1]
                t2 = tokens[i+2]
                if t1.type == 'paragraph_open' and t2.type == 'inline':
                    inline_token = t2
                    content = inline_token.content.strip()
                    match = re.match(r'^\[!(?P<type>[\w-]+)\](?:[ \t]+(?P<title>.*))?', content)
                    if match:
                        callout_type = match.group('type').lower()
                        callout_title = match.group('title') or callout_type.capitalize()
                        token.tag = 'div'
                        token.attrs = {'class': f'callout callout-{callout_type}'}
                        token.info = 'callout'
                        depth = 1
                        j = i + 1
                        while j < len(tokens):
                            if tokens[j].type == 'blockquote_open': depth += 1
                            elif tokens[j].type == 'blockquote_close':
                                depth -= 1
                                if depth == 0:
                                    tokens[j].tag = 'div'
                                    break
                            j += 1
                        title_open = Token('div_open', 'div', 1)
                        title_open.attrs = {'class': 'callout-title'}
                        icon_svg = CALLOUT_ICONS.get(callout_type, CALLOUT_ICONS["note"])
                        icon_token = Token('html_inline', '', 0)
                        icon_token.content = f'<div class="callout-icon">{icon_svg}</div>'
                        title_text = Token('inline', '', 0)
                        title_text.content = callout_title
                        title_text.children = [] 
                        title_close = Token('div_close', 'div', -1)
                        content_open = Token('div_open', 'div', 1)
                        content_open.attrs = {'class': 'callout-content'}
                        remaining_content = content[match.end():]
                        if remaining_content.startswith('\n'): remaining_content = remaining_content[1:]
                        inline_token.content = remaining_content
                        inline_token.children = []
                        new_tokens = [title_open, icon_token, title_text, title_close, content_open]
                        for t in reversed(new_tokens): tokens.insert(i+1, t)
                        j += len(new_tokens)
                        content_close = Token('div_close', 'div', -1)
                        tokens.insert(j, content_close)
                        i = i + len(new_tokens)
        i += 1

try:
    md.core.ruler.before("inline", "obsidian_callouts", obsidian_callouts)
except ValueError:
    md.core.ruler.push("obsidian_callouts", obsidian_callouts)

def process_admonition_blocks(content: str) -> str:
    lines = content.split('\n')
    output = []
    # stack of dict {'type': 'admonition'|'code', 'fence': '```', 'len': 3, 'indent': 0}
    stack = [] 

    def get_prefix():
        return "".join(["> " for item in stack if item['type'] == 'admonition'])

    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r'^(\s*)(`{3,}|~{3,})(.*)$', line)
        
        if match:
            indent_str = match.group(1)
            # Calculate visual indent (approximate tab as 4 spaces)
            indent_len = len(indent_str.replace('\t', '    '))
            fence_char = match.group(2)
            fence_len = len(fence_char)
            info = match.group(3).strip()
            
            ad_match = re.match(r'^ad-(\w+)', info)
            
            if ad_match:
                # Start Admonition
                ad_type = ad_match.group(1).lower()
                title = None
                # Check next line for title
                if i + 1 < len(lines):
                    next_line_stripped = lines[i+1].strip()
                    if next_line_stripped.startswith("title:"):
                        title = next_line_stripped[6:].strip()
                        i += 1
                if not title: title = ad_type.capitalize()
                
                prefix = get_prefix()
                output.append(f"{prefix}> [!{ad_type.upper()}] {title}")
                stack.append({
                    'type': 'admonition', 
                    'fence': fence_char[0], 
                    'len': fence_len,
                    'indent': indent_len
                })
            
            else:
                # Regular Fence (Open or Close)
                # Aggressive Closing: Close all stack items that match the fence
                any_closed = False
                
                while len(stack) > 0:
                    top = stack[-1]
                    matches = False
                    # Check for match: same char, fence length sufficient
                    if (top['fence'] == fence_char[0] and 
                        fence_len >= top['len']):
                        
                        # Indent check:
                        # If Code block: usually loose match allowed, but we might be strict
                        # If Admonition: Strict indent match required for implicit closing
                        if top['indent'] == indent_len:
                            matches = True
                    
                    if matches:
                        popped = stack.pop()
                        any_closed = True
                        if popped['type'] == 'code':
                            # Output closing fence for code block
                            prefix = get_prefix()
                            output.append(f"{prefix}{line}")
                        # If admonition, just pop (implicitly closes blockquote)
                    else:
                        break # Stop closing if mismatch
                
                if not any_closed:
                    # If nothing closed, it must be opening a code block
                    stack.append({
                        'type': 'code', 
                        'fence': fence_char[0], 
                        'len': fence_len, 
                        'indent': indent_len
                    })
                    prefix = get_prefix()
                    output.append(f"{prefix}{line}")
        else:
            prefix = get_prefix()
            output.append(f"{prefix}{line}")
        
        i += 1
    
    return '\n'.join(output)

def parse_frontmatter(content):
    frontmatter = {}
    body = content
    # Remove BOM if present
    if content.startswith('\ufeff'):
        content = content[1:]
        body = content

    # Normalized line endings to \n for easier regex matching
    content_normalized = content.replace('\r\n', '\n')

    if content_normalized.strip().startswith("---"):
        # Match allowing for leading whitespace and flexible newlines
        match = re.match(r'^\s*---\s*\n(.*?)\n---(?:\s*\n|$)', content_normalized, re.DOTALL)
        if match:
            yaml_content = match.group(1)
            try:
                frontmatter = yaml.safe_load(yaml_content) or {}
                # Calculate body offset in the ORIGINAL content
                lines = content.split('\n')
                dash_count = 0
                body_start_line = 0
                for idx, line in enumerate(lines):
                    if line.strip() == "---":
                        dash_count += 1
                        if dash_count == 2:
                            body_start_line = idx + 1
                            break
                if dash_count == 2:
                    body = '\n'.join(lines[body_start_line:])
            except yaml.YAMLError: pass
    return frontmatter, body

def parse_obsidian_date(date_str):
    if not isinstance(date_str, str): return None
    try:
        if ',' in date_str: clean_str = date_str.split(',', 1)[1].strip()
        else: clean_str = date_str.strip()
        # Use unicode escapes for Japanese "PM" and "AM"
        clean_str = clean_str.replace('\u5348\u5f8c', 'PM').replace('\u5348\u524d', 'AM')
        # Regex using unicode escapes for Month and Day
        match = re.search(r'(\d+)\u6708\s*(\d+)\u65e5\s*(\d+),\s*(\d+):(\d+):(\d+)\s*(PM|AM)', clean_str)
        if match:
            month, day, year, hour, minute, second, ampm = match.groups()
            dt_str = f"{year}-{month}-{day} {hour}:{minute}:{second} {ampm}"
            return datetime.strptime(dt_str, "%Y-%m-%d %I:%M:%S %p")
    except Exception: pass
    return None

def get_all_files(directory: Path, relative_to: Path, use_cache=True):
    # Try to load from cache first if allowed
    if use_cache and directory == CONTENT_DIR and METADATA_CACHE_FILE.exists():
        try:
            with open(METADATA_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Cache load error: {e}")

    files = []
    if not directory.exists(): return []
    encodings = ["utf-8", "cp932", "shift_jis", "euc-jp"]
    for item in directory.rglob("*.md"):
        rel_path = item.relative_to(relative_to)
        stats = item.stat()
        file_mtime = stats.st_mtime
        content = ""
        for enc in encodings:
            try:
                with open(item, "r", encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeDecodeError: continue
        frontmatter, body = parse_frontmatter(content)
        tags = frontmatter.get('tags', [])
        if isinstance(tags, str): tags = [t.strip().lstrip('#') for t in tags.split(',')]
        elif isinstance(tags, list): tags = [str(t).strip().lstrip('#') for t in tags]
        else: tags = []
        fm_date = frontmatter.get('modified') or frontmatter.get('updated')
        parsed_date = parse_obsidian_date(fm_date)
        if parsed_date:
            timestamp = parsed_date.timestamp()
            updated_str = parsed_date.strftime("%Y-%m-%d")
        else:
            timestamp = file_mtime
            updated_str = datetime.fromtimestamp(file_mtime).strftime("%Y-%m-%d")
        preview_text = body.strip()[:150]
        if len(body.strip()) > 150: preview_text += "..."
        
        # Access control: check "publish" in frontmatter
        publish_val = frontmatter.get('publish')
        is_published = False
        if isinstance(publish_val, bool):
            is_published = publish_val
        elif isinstance(publish_val, str):
            is_published = publish_val.upper() == "TRUE"

        # Use frontmatter title if available, otherwise use stem
        doc_title = frontmatter.get('title') or item.stem

        files.append({
            "name": item.name,
            "title": doc_title,
            "path": str(rel_path).replace("\\", "/"),
            "updated": updated_str,
            "timestamp": timestamp,
            "tags": tags,
            "content_lower": content.lower(),
            "preview": preview_text,
            "published": is_published
        })
    files.sort(key=lambda x: x['timestamp'], reverse=True)

    # Save to cache if it's the main scan
    if directory == CONTENT_DIR:
        try:
            with open(METADATA_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(files, f, ensure_ascii=False)
        except Exception as e:
            print(f"Cache save error: {e}")

    return files

def get_file_tree(directory: Path, relative_to: Path, published_only: bool = False):
    tree = []
    if not directory.exists(): return []
    items = list(directory.iterdir())
    items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
    for item in items:
        if item.name.startswith('.'): continue
        rel_path = item.relative_to(relative_to)
        if item.is_dir():
            children = get_file_tree(item, relative_to, published_only)
            if children:
                tree.append({
                    "type": "directory",
                    "name": item.name,
                    "path": str(rel_path).replace("\\", "/"),
                    "children": children
                })
        elif item.suffix == '.md':
            title = item.stem
            is_published = False
            try:
                encodings = ["utf-8", "cp932", "shift_jis", "euc-jp"]
                content = ""
                for enc in encodings:
                    try:
                        with open(item, "r", encoding=enc) as f:
                            # Read enough to get frontmatter
                            head = [next(f) for _ in range(20)]
                            content = "".join(head)
                        break
                    except (UnicodeDecodeError, StopIteration): continue
                fm, _ = parse_frontmatter(content)
                
                publish_val = fm.get('publish')
                if isinstance(publish_val, bool):
                    is_published = publish_val
                elif isinstance(publish_val, str):
                    is_published = publish_val.upper() == "TRUE"
            except Exception: pass
            
            if published_only and not is_published:
                continue

            tree.append({
                "type": "file",
                "name": item.name,
                "title": title,
                "path": str(rel_path).replace("\\", "/"),
            })
    return tree

def find_image_in_static(filename: str) -> str:
    images_dir = STATICS_DIR / "images"
    if not images_dir.exists(): return f"/static/images/{quote(filename)}"
    if (images_dir / filename).exists(): return f"/static/images/{quote(filename)}"
    try:
        search_name = os.path.basename(filename)
        found_file = next(images_dir.rglob(search_name))
        parts = found_file.relative_to(STATICS_DIR).parts
        encoded_parts = [quote(p) for p in parts]
        return "/static/" + "/".join(encoded_parts)
    except StopIteration:
        return f"/static/images/{quote(filename)}"

def process_obsidian_images(content: str) -> str:
    pattern = r'!\[\[([^|\]]+\.(png|jpg|jpeg|gif|svg|webp))\s*(?:\|\s*([^\]]+))?\]\]'
    def replace_image(match):
        filename = match.group(1)
        options = match.group(3)
        basename = os.path.basename(filename)
        image_url = find_image_in_static(basename)
        style_attrs = ""
        if options:
            options = options.strip()
            if 'x' in options.lower():
                parts = options.lower().split('x')
                if len(parts) == 2:
                    width = parts[0].strip()
                    height = parts[1].strip()
                    if width.isdigit() and height.isdigit():
                        style_attrs = f' width="{width}" height="{height}"'
            else:
                width = options.strip()
                if width.isdigit():
                    style_attrs = f' width="{width}"'
        alt_text = basename
        if style_attrs:
            return f'<img src="{image_url}" alt="{alt_text}" class="obsidian-image"{style_attrs}>'
        else:
            return f'![{basename}]({image_url})'
    return re.sub(pattern, replace_image, content, flags=re.IGNORECASE)

@app.get("/api/search")
async def search_files(request: Request, q: str = ""):
    q = q.lower().strip()
    if not q: return []
    
    is_local = is_request_local(request)
    all_files = get_all_files(CONTENT_DIR, CONTENT_DIR)
    
    results = []
    for f in all_files:
        # Filter unpublished files for external users
        if not is_local and not f.get('published', False):
            continue
            
        if q in f['name'].lower() or q in f['content_lower'] or q in f['title'].lower():
            results.append({
                "title": f['title'],
                "path": f['path'],
                "filename": f['name']
            })
        if len(results) >= 10: break
    return results

@app.get("/api/preview")
async def preview_file(request: Request, path: str):
    clean_path = path.strip("/")
    safe_path = (CONTENT_DIR / clean_path).resolve()
    if not str(safe_path).startswith(str(CONTENT_DIR.resolve())):
         raise HTTPException(status_code=403, detail="Access denied")
    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = ""
        encodings = ["utf-8", "cp932", "shift_jis", "euc-jp"]
        for enc in encodings:
            try:
                with open(safe_path, "r", encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeDecodeError: continue
        fm, content = parse_frontmatter(content)
        
        # Access control
        is_local = is_request_local(request)
        if not is_local:
            publish_val = fm.get('publish')
            is_published = False
            if isinstance(publish_val, bool):
                is_published = publish_val
            elif isinstance(publish_val, str):
                is_published = publish_val.upper() == "TRUE"
            
            if not is_published:
                raise HTTPException(status_code=403, detail="Access denied")

        preview_length = 500
        preview_content = content[:preview_length]
        if len(content) > preview_length: preview_content += "..."
        html_content = md.render(preview_content)
        return {
            "title": safe_path.stem,
            "content": html_content,
            "path": clean_path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, page: int = 1, q: str = "", tag: str = "", visibility: str = "all"):
    all_files = get_all_files(CONTENT_DIR, CONTENT_DIR)
    is_local = is_request_local(request)
    
    # Enforce visibility for external users
    if not is_local:
        visibility = "public"
    
    # Filter by publish status
    if visibility == "public":
        all_files = [f for f in all_files if f.get('published', False)]
    elif visibility == "private":
        all_files = [f for f in all_files if not f.get('published', False)]

    file_tree = get_file_tree(CONTENT_DIR, CONTENT_DIR, published_only=not is_local)
    all_tags = set()
    for f in all_files:
        for t in f['tags']: all_tags.add(t)
    sorted_tags = sorted(list(all_tags))
    
    filtered_files = all_files
    if tag: filtered_files = [f for f in filtered_files if tag in f['tags']]
    if q:
        q_lower = q.lower().strip()
        filtered_files = [f for f in filtered_files if q_lower in f['name'].lower() or q_lower in f['content_lower'] or q_lower in f['title'].lower()]
    
    limit = 12
    total_items = len(filtered_files)
    total_pages = math.ceil(total_items / limit)
    if page < 1: page = 1
    if page > total_pages and total_pages > 0: page = total_pages
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_files = filtered_files[start_idx:end_idx]
    
    return templates.TemplateResponse("index.html", {
        "request": request, "files": paginated_files, "title": "Obsidian-Render",
        "current_page": page, "total_pages": total_pages, "total_items": total_items,
        "q": q, "selected_tag": tag, "all_tags": sorted_tags, "file_tree": file_tree,
        "is_localhost": is_local, "visibility": visibility
    })

@app.get("/view/{file_path:path}", response_class=HTMLResponse)
async def read_item(request: Request, file_path: str):
    safe_path = (CONTENT_DIR / file_path).resolve()
    if not str(safe_path).startswith(str(CONTENT_DIR.resolve())):
         raise HTTPException(status_code=403, detail="Access denied")
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    content = ""
    encodings = ["utf-8", "cp932", "shift_jis", "euc-jp"]
    for enc in encodings:
        try:
            with open(safe_path, "r", encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError: continue
    else:
        raise HTTPException(status_code=500, detail="Could not decode file with supported encodings.")
    
    fm, content = parse_frontmatter(content)
    
    # Access control & Status
    publish_val = fm.get('publish')
    is_published = False
    if isinstance(publish_val, bool):
        is_published = publish_val
    elif isinstance(publish_val, str):
        is_published = publish_val.upper().strip() == "TRUE"
    
    is_local = is_request_local(request)
    if not is_local and not is_published:
        raise HTTPException(status_code=403, detail="Access denied")

    content = process_admonition_blocks(content)
    content = process_obsidian_images(content)
    html_content = md.render(content)
    file_tree = get_file_tree(CONTENT_DIR, CONTENT_DIR, published_only=not is_local)
    
    # Use frontmatter title if available
    doc_title = fm.get('title') or safe_path.stem
    
    return templates.TemplateResponse("view.html", {
        "request": request, "content": html_content, "title": doc_title,
        "filename": safe_path.name, "file_tree": file_tree, "is_localhost": is_local,
        "is_published": is_published
    })

# --- File Sync Feature ---
import shutil
import asyncio
from pydantic import BaseModel

CONFIG_FILE = BASE_DIR / "server_config.yaml"

class SyncConfig(BaseModel):
    sync_enabled: bool = False
    auto_sync_enabled: bool = False
    content_src: str = ""
    images_src: str = ""
    interval_minutes: int = 60
    last_sync: str = ""

def load_config() -> SyncConfig:
    if not CONFIG_FILE.exists():
        return SyncConfig()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return SyncConfig(**data)
    except Exception:
        return SyncConfig()

def save_config(config: SyncConfig):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config.dict(), f)

def perform_sync(config: SyncConfig):
    if not config.sync_enabled: return
    
    # Sync Content
    if config.content_src and os.path.exists(config.content_src):
        src_path = Path(config.content_src)
        for item in src_path.rglob("*.md"):
            try:
                rel_path = item.relative_to(src_path)
                dest_path = CONTENT_DIR / rel_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                if not dest_path.exists() or item.stat().st_mtime > dest_path.stat().st_mtime:
                    shutil.copy2(item, dest_path)
            except Exception as e:
                print(f"Error syncing {item}: {e}")

    # Sync Images
    if config.images_src and os.path.exists(config.images_src):
        src_path = Path(config.images_src)
        # Extensions to sync
        extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
        for item in src_path.rglob("*"):
            if item.suffix.lower() in extensions:
                try:
                    rel_path = item.relative_to(src_path)
                    dest_path = STATICS_DIR / "images" / rel_path
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    if not dest_path.exists() or item.stat().st_mtime > dest_path.stat().st_mtime:
                        shutil.copy2(item, dest_path)
                except Exception as e:
                    print(f"Error syncing {item}: {e}")
    
    # Update last sync time
    jst = timezone(timedelta(hours=9))
    config.last_sync = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")
    save_config(config)

    # Force metadata cache refresh
    get_all_files(CONTENT_DIR, CONTENT_DIR, use_cache=False)

background_task_running = False

async def background_sync_loop():
    global background_task_running
    if background_task_running: return
    background_task_running = True
    while True:
        config = load_config()
        if config.sync_enabled and config.auto_sync_enabled:
            perform_sync(config)
            # Wait for interval (minutes to seconds)
            await asyncio.sleep(config.interval_minutes * 60)
        else:
            # If disabled, check again in 1 minute
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(background_sync_loop())

def is_request_local(request: Request) -> bool:
    # 接続元IPをチェック (Docker等のブリッジ通信 172.x なども許容)
    client_host = request.client.host
    is_ip_local = (
        client_host in ("127.0.0.1", "::1") or
        client_host.startswith("172.") or
        client_host.startswith("192.168.") or
        client_host.startswith("10.")
    )
    
    if is_ip_local:
        return True

    # Hostヘッダーをチェック (ブラウザのアドレスバーの内容)
    # 外部デバイスからIP直打ちアクセスされた場合も、client_hostがローカルならOK
    host_header = request.headers.get("host", "").split(":")[0].lower()
    is_host_local = host_header in ("localhost", "127.0.0.1", "[::1]")
    
    return is_host_local

def check_localhost(request: Request):
    if not is_request_local(request):
        print(f"Access denied for host: {request.client.host}") # Log the rejected host
        raise HTTPException(status_code=403, detail="Access denied")

@app.get("/api/config")
async def get_config(request: Request):
    check_localhost(request)
    return load_config()

@app.post("/api/config")
async def update_config(request: Request, config: SyncConfig):
    check_localhost(request)
    
    # Validation
    errors = {}
    if config.sync_enabled:
        # Check content_src
        if not config.content_src:
            errors["content_src"] = "コンテンツフォルダのパスを入力してください。"
        else:
            path = Path(config.content_src)
            if not path.exists() or not path.is_dir():
                errors["content_src"] = "指定されたディレクトリが存在しません。"
            else:
                # Recursively check for .md files
                md_found = any(path.rglob("*.md"))
                if not md_found:
                    errors["content_src"] = "指定されたフォルダに .md ファイルが見つかりません。"
        
        # Check images_src (optional, but if provided, must be valid)
        if config.images_src:
            path = Path(config.images_src)
            if not path.exists() or not path.is_dir():
                errors["images_src"] = "指定されたディレクトリが存在しません。"
            else:
                # Recursively check for images
                extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
                img_found = any(p.suffix.lower() in extensions for p in path.rglob("*") if p.is_file())
                if not img_found:
                    errors["images_src"] = "指定されたフォルダに画像ファイルが見当たりません。"

    if errors:
        return JSONResponse(status_code=400, content={"status": "error", "errors": errors})

    save_config(config)
    return {"status": "ok", "config": config}

@app.post("/api/sync")
async def trigger_sync(request: Request):
    check_localhost(request)
    config = load_config()
    perform_sync(config)
    return {"status": "ok", "last_sync": config.last_sync}

@app.post("/api/rebuild-index")
async def rebuild_index(request: Request):
    check_localhost(request)
    # Scan without cache and force update the file
    get_all_files(CONTENT_DIR, CONTENT_DIR, use_cache=False)
    return {"status": "ok"}

@app.get("/api/list-dirs")
async def list_dirs(request: Request, path: str = "/"):
    check_localhost(request)
    try:
        target_path = Path(path)
        if not target_path.exists() or not target_path.is_dir():
            return JSONResponse(status_code=400, content={"status": "error", "message": "Invalid directory"})
        
        dirs = []
        # Support parent dir navigation
        parent = str(target_path.parent) if target_path != target_path.parent else None
        
        # List subdirectories (sorted)
        try:
            for item in sorted(target_path.iterdir()):
                if item.is_dir():
                    try:
                        # Permission check
                        item.iterdir()
                        dirs.append({
                            "name": item.name,
                            "path": str(item).replace("\\", "/")
                        })
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            return JSONResponse(status_code=403, content={"status": "error", "message": "Permission denied"})

        return {
            "status": "ok",
            "current": str(target_path).replace("\\", "/"),
            "parent": parent.replace("\\", "/") if parent else None,
            "dirs": dirs
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
