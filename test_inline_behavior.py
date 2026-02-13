
from markdown_it import MarkdownIt
from markdown_it.token import Token

md = MarkdownIt("commonmark", {"breaks": True, "html": True})

def test_plugin(state):
    t = Token('inline', '', 0)
    t.content = "Content with empty children"
    t.children = []
    
    t2 = Token('inline', '', 0)
    t2.content = "Content with text child"
    child = Token('text', '', 0)
    child.content = "Content with text child"
    t2.children = [child]
    
    state.tokens.append(t)
    state.tokens.append(Token('hardbreak', '', 0))
    state.tokens.append(t2)

md.core.ruler.push("test", test_plugin)

html = md.render("")
print(f"HTML Output:\n{html}")
