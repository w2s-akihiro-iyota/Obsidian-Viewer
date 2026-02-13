
from markdown_it import MarkdownIt
import re
from markdown_it.token import Token

CALLOUT_ICONS = {"note": "ICON"}

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
                    print(f"DEBUG: inline_token.content = {repr(content)}")
                    print(f"DEBUG: inline_token.children = {[c.type for c in inline_token.children]}")
                    
                    match = re.match(r'^\[!(?P<type>[\w-]+)\](?:\s+(?P<title>.*))?', content)
                    if match:
                        callout_type = match.group('type').lower()
                        callout_title = match.group('title') or callout_type.capitalize()
                        print(f"DEBUG: Detected Type: {callout_type}")
                        print(f"DEBUG: Detected Title: {callout_title}")
                        
                        # Logic simulation
                        remaining_content = content[match.end():]
                        print(f"DEBUG: remaining_content before fix: {repr(remaining_content)}")
                        
                        if remaining_content.startswith('\n'): remaining_content = remaining_content[1:]
                        print(f"DEBUG: final content: {repr(remaining_content)}")

        i += 1

md = MarkdownIt("commonmark", {"breaks": True, "html": True})
md.core.ruler.push("obsidian_callouts", obsidian_callouts)

text = """> [!NOTE]
> This is a note callout"""

print("--- Testing Case 1: Newline ---")
html = md.render(text)
print("-" * 20)

text2 = """> [!NOTE] This is a title
> This is content"""

print("\n--- Testing Case 2: Explicit Title ---")
html2 = md.render(text2)
