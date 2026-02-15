
from markdown_it import MarkdownIt
try:
    from main import obsidian_callouts
except ImportError:
    print("Could not import from main, using mock (this should not happen if main.py is correct)")
    # ... mock definition ...

md = MarkdownIt("commonmark", {"breaks": True, "html": True})
try:
    md.core.ruler.before("inline", "obsidian_callouts", obsidian_callouts)
except ValueError:
    md.core.ruler.push("obsidian_callouts", obsidian_callouts)

print("--- Testing Case 1: Newline (Should meet user req) ---")
# User wants:
# > [!NOTE]
# > Content
# To be: Title="Note" (default), Content="Content"
text = """> [!NOTE]
> This is content"""
html = md.render(text)
print(f"HTML Output:\n{html}")

print("\n--- Testing Case 2: Explicit Title ---")
text2 = """> [!NOTE] Custom Title
> This is content"""
html2 = md.render(text2)
print(f"HTML Output:\n{html2}")
