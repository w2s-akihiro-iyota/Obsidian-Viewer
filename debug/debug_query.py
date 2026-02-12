import urllib.request
import urllib.parse
import json

base_url = "http://127.0.0.1:8018/debug_tokens"

cases = [
    """# Highlight and Callout Test

This text contains ==highlighted text== using the `==` syntax.

## Callouts

> [!NOTE] Test Note
> This is a note callout.
> It works like Obsidian.

> [!WARNING]
> This is a warning without a specific title.
"""
]

for c in cases:
    print(f"--- Case: {repr(c)} ---")
    query = urllib.parse.quote(c)
    url = f"{base_url}?text={query}"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
            # Print simplified structure
            for t in data:
                print(f"Type: {t['type']}, Tag: {t['tag']}, Info: {t.get('info', '')}")
                if t['type'] == 'inline':
                    print(f"  Content: {repr(t['content'])}")
    except Exception as e:
        print(f"Error: {e}")
