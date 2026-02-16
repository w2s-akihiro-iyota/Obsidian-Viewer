import markdown_it
from markdown_it.tree import SyntaxTreeNode
from markdown_it.token import Token
import re
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

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

# MarkdownIt Instance
md = (
    markdown_it.MarkdownIt("commonmark", {"breaks": True, "html": True})
    .enable("table")
    .enable("strikethrough")
    .use(mark_plugin)
    .use(dollarmath_plugin)
    .use(tasklists_plugin)
)

# Cardlink renderer
default_fence_renderer = md.renderer.rules.get("fence", markdown_it.renderer.RendererHTML.fence)

def render_cardlink(tokens, idx, options, env):
    token = tokens[idx]
    if token.info.strip() == "cardlink":
        lines = token.content.strip().split('\n')
        data = {}
        for line in lines:
            if ':' in line:
                k, v = line.split(':', 1)
                data[k.strip()] = v.strip()
        
        title = data.get('title', 'No Title')
        url = data.get('url', '#')
        desc = data.get('description', '')
        image = data.get('image', '')
        
        img_html = f'<div class="link-card-image" style="background-image: url({image})"></div>' if image else ''
        return f"""
        <a href="{url}" class="link-card" target="_blank" rel="noopener noreferrer">
            <div class="link-card-content">
                <div class="link-card-title">{title}</div>
                <div class="link-card-description">{desc}</div>
                <div class="link-card-meta">{url}</div>
            </div>
            {img_html}
        </a>
        """
    # Important: Fallback to default for other code blocks
    return default_fence_renderer(tokens, idx, options, env)

md.renderer.rules["fence"] = render_cardlink

# Icons mapping
CALLOUT_ICONS = {
    "note": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-pencil"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>""",
    "abstract": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-list"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>""",
    "info": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-info"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>""",
    "todo": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check-circle-2"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>""",
    "tip": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-flame"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>""",
    "success": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-check-square"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>""",
    "warning": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-alert-triangle"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>""",
    "failure": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-x-circle"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>""",
    "danger": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-zap"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></polygon></svg>""",
    "bug": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-bug"><rect width="8" height="14" x="8" y="6" rx="4"/><path d="m19 7-3 2"/><path d="m5 7 3 2"/><path d="m19 19-3-2"/><path d="m5 19 3-2"/><path d="M20 13h-4"/><path d="M4 13h4"/><path d="m10 4 1 2"/><path d="m14 4-1 2"/></svg>""",
    "example": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-beaker"><path d="M4.5 3h15"/><path d="M6 3v16a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V3"/><path d="M6 14h12"/></svg>""",
    "quote": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-quote"><path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 2.5 1 4.5 8.5 8.291"/><path d="M21 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 2.5 1 4.5 8.5 8.291"/></svg>""",
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
