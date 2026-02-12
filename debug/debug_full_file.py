import urllib.request
import urllib.parse
import json

base_url = "http://127.0.0.1:8014/debug_tokens"

with open("content/test_features.md", "r", encoding="utf-8") as f:
    text = f.read()

print(f"File text length: {len(text)}")

query = urllib.parse.quote(text)
url = f"{base_url}?text={query}"

try:
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode('utf-8'))
        print(f"Total tokens: {len(data)}")
        for i, t in enumerate(data):
            if t['type'] == 'blockquote_open':
                print(f"Blockquote at {i}: Tag={t['tag']}, Info={t.get('info', '')}")
                # Print next few tokens
                if i+2 < len(data):
                    t2 = data[i+2]
                    print(f"  Token+2: Type={t2['type']}, Content={repr(t2['content'])}")
            if t['type'] == 'div_open' and 'callout' in t.get('attrs', {}).get('class', ''):
                 print(f"Callout Div at {i}: Type={t['type']}, Class={t['attrs']['class']}")

except Exception as e:
    print(f"Error: {e}")
