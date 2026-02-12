from main import md
import json

def serialize_token(token):
    return {
        "type": token.type,
        "tag": token.tag,
        "content": token.content,
        "children": [serialize_token(c) for c in token.children] if token.children else [],
        "info": token.info
    }

src = "> [!NOTE] Title\n> Content"
tokens = md.parse(src)
print(json.dumps([serialize_token(t) for t in tokens], indent=2))
