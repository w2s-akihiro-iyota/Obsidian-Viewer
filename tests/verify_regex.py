
import re

regex_original = r'^\[!(?P<type>[\w-]+)\](?:\s+(?P<title>.*))?'
regex_fix = r'^\[!(?P<type>[\w-]+)\](?:[ \t]+(?P<title>.*))?'

cases = [
    "[!NOTE]\nThis is content",
    "[!NOTE] Title\nContent",
    "[!NOTE] Title",
    "[!TIP]\tTitle with tab",
]

print("--- Original Regex ---")
for text in cases:
    match = re.match(regex_original, text)
    if match:
        print(f"Text: {repr(text)}")
        print(f"  Type: {match.group('type')}")
        print(f"  Title: {repr(match.group('title'))}")
    else:
        print(f"Text: {repr(text)} -> No match")

print("\n--- Fixed Regex ---")
for text in cases:
    match = re.match(regex_fix, text)
    if match:
        print(f"Text: {repr(text)}")
        print(f"  Type: {match.group('type')}")
        print(f"  Title: {repr(match.group('title'))}")
    else:
        print(f"Text: {repr(text)} -> No match")
