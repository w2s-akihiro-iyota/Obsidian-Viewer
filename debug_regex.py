import re

content = '[!NOTE] Test Note\nThis is a note callout.\nIt works like Obsidian.'
pattern = r'^\[!(?P<type>[\w-]+)\](?:\s+(?P<title>.*))?'

match = re.match(pattern, content)
print(f"Content: {repr(content)}")
print(f"Pattern: {pattern}")
if match:
    print("MATCH!")
    print(f"Type: {match.group('type')}")
    print(f"Title: {match.group('title')}")
else:
    print("NO MATCH")
