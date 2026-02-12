from main import md
import json

def serialize_token(token):
    return {
        "type": token.type,
        "tag": token.tag,
        "content": token.content,
        "info": token.info
        # "children": [serialize_token(c) for c in token.children] if token.children else [],
    }

with open("content/test_features.md", "r", encoding="utf-8") as f:
    src = f.read()

print(f"File Source Length: {len(src)}")
print(f"First 200 chars: {repr(src[:200])}")

tokens = md.parse(src)

# Filter for blockquote tokens and their content
for i, token in enumerate(tokens):
    if token.type == 'blockquote_open':
        print(f"Found blockquote at index {i}")
        # Look ahead
        if i+2 < len(tokens):
            t2 = tokens[i+2]
            print(f"  Token+2 type: {t2.type}, content: {repr(t2.content)}")
