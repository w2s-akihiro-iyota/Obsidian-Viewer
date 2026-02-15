import re
import yaml

def parse_frontmatter(content):
    frontmatter = {}
    body = content
    # Use a more robust check for the start
    if content.strip().startswith("---"):
        # Match from the start, allowing for potential BOM or leading space
        match = re.match(r'^\s*---\s*\n(.*?)\n---\s*\n?', content, re.DOTALL)
        if not match:
            # Try with \r\n explicitly if \n is tricky
            match = re.match(r'^\s*---\s*\r?\n(.*?)\r?\n---\s*\r?\n?', content, re.DOTALL)
            
        if match:
            yaml_content = match.group(1)
            try:
                frontmatter = yaml.safe_load(yaml_content) or {}
                body = content[match.end():]
            except Exception as e:
                print(f"YAML Error: {e}")
        else:
            print("Regex did not match.")
    else:
        print("Content does not start with ---")
    return frontmatter, body

# Actual content of demo.md (mocked)
with open(r"d:\SANDBOX\Antigravity\Obsidian-Viewer\content\samples\demo.md", "r", encoding="utf-8") as f:
    content = f.read()

print(f"Content starts with: {repr(content[:10])}")
fm, body = parse_frontmatter(content)
print(f"Parsed Frontmatter: {fm}")
print(f"Body starts with: {repr(body[:20])}")
