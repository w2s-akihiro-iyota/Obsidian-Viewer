
from main import process_admonition_blocks

content = """
```ad-question
Outer
```ad-success
Inner
```
Trailing Text
"""

processed = process_admonition_blocks(content)
print("--- PROCESSED OUTPUT ---")
print(processed)
print("------------------------")

# Check if "Trailing Text" is inside the blockquote
lines = processed.split('\n')
trailing_line = lines[-2] # Empty line before?
# Find line with "Trailing Text"
for line in lines:
    if "Trailing Text" in line:
        if line.strip().startswith(">"):
            print("RESULT: Trailing Text is INSIDE Admonition")
        else:
            print("RESULT: Trailing Text is OUTSIDE Admonition")
