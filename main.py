from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import markdown_it
from markdown_it.tree import SyntaxTreeNode
import os
from datetime import datetime
import yaml
import re
import math
from urllib.parse import quote

app = FastAPI(title="Obsidian Viewer")

# Configuration
# serves files from 'content' directory by default, or current dir if not exists
# For safety in this environment, we'll create a content dir.
BASE_DIR = Path(__file__).resolve().parent
CONTENT_DIR = BASE_DIR / "content"
if not CONTENT_DIR.exists():
    CONTENT_DIR.mkdir()

# Static Files
STATICS_DIR = BASE_DIR / "static"
if not STATICS_DIR.exists():
    STATICS_DIR.mkdir()
app.mount("/static", StaticFiles(directory=str(STATICS_DIR)), name="static")

# Templates
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Markdown Setup
# Custom Mark Plugin (Simple)
def mark_plugin(md):
    def mark(state, silent):
        start = state.pos
        marker = '=='
        
        if state.src[start:start+2] != marker:
            return False
            
        # Find closing ==
        found = False
        pos = start + 2
        while pos < state.posMax - 1:
            if state.src[pos:pos+2] == marker:
                found = True
                break
            pos += 1
            
        if not found:
            return False
            
        if silent:
            return True
            
        state.pos = start + 2
        state.push('mark_open', 'mark', 1)
        
        # Note: This limits nested markdown inside highlights for now
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

# Store the original fence renderer
default_fence_renderer = md.renderer.rules.get("fence", markdown_it.renderer.RendererHTML.fence)

# Store the original fence renderer
default_fence_renderer = md.renderer.rules.get("fence", markdown_it.renderer.RendererHTML.fence)

def render_cardlink(tokens, idx, options, env):
    token = tokens[idx]
    info = token.info.strip()
    
    if info == 'cardlink':
        try:
            data = yaml.safe_load(token.content)
            # Handle potential list or single dict
            if isinstance(data, list):
                data = data[0]
            if not isinstance(data, dict):
                raise ValueError("Invalid data format")

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
        except Exception as e:
            pass # Fallback to default
    
    # Fallback to default fence renderer
    return default_fence_renderer(tokens, idx, options, env)

md.renderer.rules["fence"] = render_cardlink

from markdown_it.token import Token

def process_admonition_blocks(content: str) -> str:
    """
    Process Obsidian Admonition-style code blocks (```ad-TYPE) and convert to callout HTML.
    This runs before markdown-it parsing so content inside can still be processed as markdown.
    """
    # Pattern to match ```ad-TYPE blocks
    pattern = r'```ad-(\w+)\s*\n(.*?)```'
    
    def replace_admonition(match):
        ad_type = match.group(1).lower()
        block_content = match.group(2).rstrip()
        
        # Extract title if present
        title = None
        lines = block_content.split('\n')
        if lines and lines[0].strip().startswith('title:'):
            title_line = lines[0].strip()
            title = title_line[6:].strip()  # Remove 'title:' prefix
            # Remove title line from content
            block_content = '\n'.join(lines[1:]).lstrip('\n')
        
        # If no title specified, use the type name capitalized
        if not title:
            title = ad_type.capitalize()
        
        # Get icon for this type
        icon_svg = CALLOUT_ICONS.get(ad_type, CALLOUT_ICONS.get("note", ""))
        
        # Build callout HTML structure
        # We use blockquote format so markdown-it can process the content
        callout_html = f'''> [!{ad_type.upper()}] {title}
> {block_content.replace(chr(10), chr(10) + "> ")}'''
        
        return callout_html
    
    # Replace all admonition blocks
    result = re.sub(pattern, replace_admonition, content, flags=re.DOTALL)
    return result

def process_obsidian_images(content: str) -> str:
    """
    Process Obsidian-style image syntax ![[filename.png]] and convert to standard Markdown.
    Images are expected to be in the static/images directory.
    
    Supports: PNG, JPG, JPEG, GIF, SVG, WEBP (case-insensitive)
    Options: |WIDTH or |WIDTHxHEIGHT (spaces around | are allowed)
    """
    # Pattern to match ![[filename.ext]] or ![[filename.ext|options]] or ![[filename.ext | options]]
    # Group 1: filename with extension
    # Group 2: extension
    # Group 3: options (optional)
    # \s* allows spaces before and after the pipe
    pattern = r'!\[\[([^|\]]+\.(png|jpg|jpeg|gif|svg|webp))\s*(?:\|\s*([^\]]+))?\]\]'
    
    def replace_image(match):
        filename = match.group(1)
        extension = match.group(2)
        options = match.group(3)  # May be None
        
        # Extract basename (handles paths like "subfolder/image.png")
        basename = os.path.basename(filename)
        # URL-encode the filename (handles spaces and special characters)
        encoded_basename = quote(basename)
        
        # Parse options for size
        style_attrs = ""
        if options:
            options = options.strip()
            # Pattern 1: WIDTHxHEIGHT (e.g., "500x300")
            # Pattern 2: WIDTH only (e.g., "500")
            if 'x' in options.lower():
                # Width x Height format
                parts = options.lower().split('x')
                if len(parts) == 2:
                    width = parts[0].strip()
                    height = parts[1].strip()
                    # Validate that both are numeric
                    if width.isdigit() and height.isdigit():
                        style_attrs = f' width="{width}" height="{height}"'
            else:
                # Width only format
                width = options.strip()
                if width.isdigit():
                    style_attrs = f' width="{width}"'
        
        # Generate HTML img tag with size attributes if options were provided
        alt_text = basename
        if style_attrs:
            # Return HTML img tag directly with obsidian-image class for styling
            return f'<img src="/static/images/{encoded_basename}" alt="{alt_text}" class="obsidian-image"{style_attrs}>'
        else:
            # Return standard Markdown syntax (for backward compatibility)
            # Add class via markdown-it rendering if needed
            return f'![{basename}](/static/images/{encoded_basename})'
    
    return re.sub(pattern, replace_image, content, flags=re.IGNORECASE)


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

# Callout / Admonition Plugin Logic
# We'll use a core rule to transform blockquotes that look like callouts into containers
def obsidian_callouts(state):
    tokens = state.tokens
    i = 0
    while i < len(tokens):
        token = tokens[i]
        
        # Check for blockquote open
        if token.type == 'blockquote_open':
            # Look ahead for paragraph open and inline content
            if i + 2 < len(tokens):
                t1 = tokens[i+1]
                t2 = tokens[i+2]
                if t1.type == 'paragraph_open' and t2.type == 'inline':
                    inline_token = t2
                    content = inline_token.content.strip()
                
                # Regex to match > [!TYPE] Title
                match = re.match(r'^\[!(?P<type>[\w-]+)\](?:\s+(?P<title>.*))?', content)
                if match:
                    callout_type = match.group('type').lower()
                    callout_title = match.group('title') or callout_type.capitalize()
                    
                    # Modify the blockquote token to be a div with callout class
                    callout_title = match.group('title') or callout_type.capitalize()
                    
                    # Modify the blockquote token to be a div with callout class
                    token.tag = 'div'
                    token.attrs = {'class': f'callout callout-{callout_type}'}
                    token.info = 'callout' # Mark as callout
                    
                    # Find and modify the matching close token
                    depth = 1
                    j = i + 1
                    while j < len(tokens):
                        if tokens[j].type == 'blockquote_open':
                            depth += 1
                        elif tokens[j].type == 'blockquote_close':
                            depth -= 1
                            if depth == 0:
                                tokens[j].tag = 'div' # Close the div
                                break
                        j += 1
                    
                    # Create title tokens
                    title_open = Token('div_open', 'div', 1)
                    title_open.attrs = {'class': 'callout-title'}
                    
                    # Icon token (static html)
                    icon_svg = CALLOUT_ICONS.get(callout_type, CALLOUT_ICONS["note"])
                    icon_token = Token('html_inline', '', 0)
                    icon_token.content = f'<div class="callout-icon">{icon_svg}</div>'
                    
                    # We create an inline token for the title content.
                    # Since we run BEFORE 'inline' rule, this token will be parsed later.
                    title_text = Token('inline', '', 0)
                    title_text.content = callout_title
                    title_text.children = [] 
                    
                    title_close = Token('div_close', 'div', -1)
                    
                    content_open = Token('div_open', 'div', 1)
                    content_open.attrs = {'class': 'callout-content'}
                    
                    # Update the original inline token content to remove the marker
                    remaining_content = content[match.end():]
                    if remaining_content.startswith('\n'):
                        remaining_content = remaining_content[1:]
                    
                    inline_token.content = remaining_content
                    inline_token.children = [] # Reset children just in case
                    
                    new_tokens = [title_open, icon_token, title_text, title_close, content_open]
                    for t in reversed(new_tokens):
                        tokens.insert(i+1, t)
                    
                    # Find the closing tag to insert content_close
                    j += len(new_tokens)
                    content_close = Token('div_close', 'div', -1)
                    tokens.insert(j, content_close)
                    
                    # Skip the tokens we handled/inserted
                    i = i + len(new_tokens)
                    
        i += 1

# Hook before 'inline' rule so that our new inline tokens get parsed
try:
    md.core.ruler.before("inline", "obsidian_callouts", obsidian_callouts)
except ValueError:
    # If inline doesn't exist (unlikely in core), fallback to push
    md.core.ruler.push("obsidian_callouts", obsidian_callouts)

# Frontmatter Parser
def parse_frontmatter(content):
    """
    Parse frontmatter from content.
    Returns tuple: (frontmatter_dict, body_content)
    """
    frontmatter = {}
    body = content
    
    if content.startswith("---"):
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n?', content, re.DOTALL)
        if match:
            yaml_content = match.group(1)
            try:
                frontmatter = yaml.safe_load(yaml_content) or {}
            except yaml.YAMLError:
                pass
            body = content[match.end():]
    
    return frontmatter, body


def parse_obsidian_date(date_str):
    """
    Parses Obsidian date format like: "火曜日, 3月 4日 2025, 4:03:46 午後"
    """
    if not isinstance(date_str, str):
        return None
        
    try:
        # Remove weekday (everything before first comma) if present
        if ',' in date_str:
            clean_str = date_str.split(',', 1)[1].strip()
        else:
            clean_str = date_str.strip()
            
        # Replace Japanese AM/PM
        clean_str = clean_str.replace('午後', 'PM').replace('午前', 'AM')
        
        # Extract parts using regex
        # Expected format after cleanup: "3月 4日 2025, 4:03:46 PM"
        # Regex to handle "Month月 Day日 Year, Time AM/PM"
        match = re.search(r'(\d+)月\s*(\d+)日\s*(\d+),\s*(\d+):(\d+):(\d+)\s*(PM|AM)', clean_str)
        
        if match:
            month, day, year, hour, minute, second, ampm = match.groups()
            dt_str = f"{year}-{month}-{day} {hour}:{minute}:{second} {ampm}"
            return datetime.strptime(dt_str, "%Y-%m-%d %I:%M:%S %p")
    except Exception:
        pass
            
    return None

def get_all_files(directory: Path, relative_to: Path):
    """
    Recursively get list of markdown files with metadata.
    Reads file content to extract tags and frontmatter.
    """
    files = []
    if not directory.exists():
        return []
    
    encodings = ["utf-8", "cp932", "shift_jis", "euc-jp"]
    
    for item in directory.rglob("*.md"):
        rel_path = item.relative_to(relative_to)
        stats = item.stat()
        file_mtime = stats.st_mtime
        
        content = ""
        # Read content for search and tags
        for enc in encodings:
            try:
                with open(item, "r", encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        frontmatter, body = parse_frontmatter(content)
        tags = frontmatter.get('tags', [])
        # Normalize tags to list
        if isinstance(tags, str):
            tags = [t.strip().lstrip('#') for t in tags.split(',')]
        elif isinstance(tags, list):
            tags = [str(t).strip().lstrip('#') for t in tags]
        else:
            tags = []

        # Determine Update Date
        # Priority: frontmatter 'modified' > frontmatter 'updated' > file mtime
        fm_date = frontmatter.get('modified') or frontmatter.get('updated')
        parsed_date = parse_obsidian_date(fm_date)
        
        if parsed_date:
            timestamp = parsed_date.timestamp()
            updated_str = parsed_date.strftime("%Y-%m-%d")
        else:
            timestamp = file_mtime
            updated_str = datetime.fromtimestamp(file_mtime).strftime("%Y-%m-%d")

        # Extract content preview (first 150 characters of body)
        preview_text = body.strip()[:150]
        if len(body.strip()) > 150:
            preview_text += "..."
        
        files.append({
            "name": item.name,
            "title": item.stem, # Default title
            "path": str(rel_path).replace("\\", "/"),
            "updated": updated_str,
            "timestamp": timestamp,
            "tags": tags,
            "content_lower": content.lower(), # Cache lower content for search
            "preview": preview_text #  Content preview
        })
    
    # Sort by updated desc by default
    files.sort(key=lambda x: x['timestamp'], reverse=True)
    return files

def get_file_tree(directory: Path, relative_to: Path):
    """
    Recursively build a tree structure of files and directories.
    """
    tree = []
    if not directory.exists():
        return []
    
    # Get all items
    items = list(directory.iterdir())
    # Sort: Directories first, then files. Alphabetical within groups.
    items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
    
    for item in items:
        # Skip hidden files/dirs
        if item.name.startswith('.'):
            continue
            
        rel_path = item.relative_to(relative_to)
        
        if item.is_dir():
            children = get_file_tree(item, relative_to)
            if children: # Only add directories if they have content
                tree.append({
                    "type": "directory",
                    "name": item.name,
                    "path": str(rel_path).replace("\\", "/"),
                    "children": children
                })
        elif item.suffix == '.md':
            # Get title from frontmatter if possible, else filename
            title = item.stem
            try:
                # Basic read to find title
                encodings = ["utf-8", "cp932", "shift_jis", "euc-jp"]
                content = ""
                for enc in encodings:
                    try:
                        with open(item, "r", encoding=enc) as f:
                            # Read first few lines for frontmatter
                            head = [next(f) for _ in range(10)]
                            content = "".join(head)
                        break
                    except (UnicodeDecodeError, StopIteration):
                        continue
                
                fm, _ = parse_frontmatter(content)
                # We could use title from frontmatter, but for tree, filename is often better
                # or we can stick to stem. Let's stick to stem for consistency with file explorer.
            except Exception:
                pass

            tree.append({
                "type": "file",
                "name": item.name,
                "title": title,
                "path": str(rel_path).replace("\\", "/"),
            })
            
    return tree

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, page: int = 1, q: str = "", tag: str = ""):
    all_files = get_all_files(CONTENT_DIR, CONTENT_DIR)
    file_tree = get_file_tree(CONTENT_DIR, CONTENT_DIR)
    
    # Collect all unique tags
    all_tags = set()
    for f in all_files:
        for t in f['tags']:
            all_tags.add(t)
    sorted_tags = sorted(list(all_tags))

    # Filter
    filtered_files = all_files
    
    # Tag Filter
    if tag:
        filtered_files = [f for f in filtered_files if tag in f['tags']]
        
    # Text Search Filter
    if q:
        q_lower = q.lower().strip()
        filtered_files = [
            f for f in filtered_files 
            if q_lower in f['name'].lower() or q_lower in f['content_lower']
        ]

    # Pagination
    limit = 12
    total_items = len(filtered_files)
    total_pages = math.ceil(total_items / limit)
    
    if page < 1: page = 1
    if page > total_pages and total_pages > 0: page = total_pages
    
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    
    paginated_files = filtered_files[start_idx:end_idx]
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "files": paginated_files, 
            "title": "Obsidian-Render",
            # Pagination & Search Data
            "current_page": page,
            "total_pages": total_pages,
            "total_items": total_items,
            "q": q,
            "selected_tag": tag,
            "all_tags": sorted_tags,
            "file_tree": file_tree 
        }
    )

@app.get("/api/search")
async def search_files(q: str = ""):
    """Search for files containing the query string."""
    q = q.lower().strip()
    if not q:
        return []
    
    results = []
    # Recursively search content
    for item in CONTENT_DIR.rglob("*.md"):
        try:
            content = ""
            encodings = ["utf-8", "cp932", "shift_jis", "euc-jp"]
            for enc in encodings:
                try:
                    with open(item, "r", encoding=enc) as f:
                        content = f.read().lower()
                    break
                except UnicodeDecodeError:
                    continue
            
            # Simple substring match in filename or content
            if q in item.name.lower() or q in content:
                rel_path = item.relative_to(CONTENT_DIR)
                results.append({
                    "title": item.stem,
                    "path": str(rel_path).replace("\\", "/"),
                    "filename": item.name
                })
        except Exception:
            continue
            
            
    return results[:10] # Limit results

@app.get("/api/preview")
async def preview_file(path: str):
    """Return a preview of the file content."""
    # Handle both relative path from content dir and potential absolute-looking paths
    # generated by the frontend
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
            except UnicodeDecodeError:
                continue
        
        # Parse frontmatter
        fm, content = parse_frontmatter(content)
        
        # Preview strategy: 
        # 1. Strip frontmatter
        # 2. Get first 500 characters
        # 3. Render markdown
        
        preview_length = 500
        preview_content = content[:preview_length]
        if len(content) > preview_length:
            preview_content += "..."
            
        # Basic markdown rendering for preview
        html_content = md.render(preview_content)
        
        return {
            "title": safe_path.stem,
            "content": html_content,
            "path": clean_path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/view/{file_path:path}", response_class=HTMLResponse)
async def read_item(request: Request, file_path: str):
    # Security check to prevent directory traversal
    safe_path = (CONTENT_DIR / file_path).resolve()
    if not str(safe_path).startswith(str(CONTENT_DIR.resolve())):
         raise HTTPException(status_code=403, detail="Access denied")
    
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    content = ""
    # Try different encodings
    encodings = ["utf-8", "cp932", "shift_jis", "euc-jp"]
    for enc in encodings:
        try:
            with open(safe_path, "r", encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        # If all encodings fail
        raise HTTPException(status_code=500, detail="Could not decode file with supported encodings.")

    # Frontmatter Hiding
    # Parse using helper
    _, content = parse_frontmatter(content)

    # Process admonition-style code blocks (```ad-XXX)
    content = process_admonition_blocks(content)

    # Process Obsidian-style image syntax (![[image.png]])
    content = process_obsidian_images(content)

    html_content = md.render(content)
    
    file_tree = get_file_tree(CONTENT_DIR, CONTENT_DIR)

    return templates.TemplateResponse(
        "view.html", 
        {
            "request": request, 
            "content": html_content, 
            "title": safe_path.stem,
            "filename": safe_path.name,
            "file_tree": file_tree
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
