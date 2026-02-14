
import re

def process_admonition_blocks_stack(content: str) -> str:
    lines = content.split('\n')
    output = []
    stack = [] # List of 'admonition' or 'code'
    
    # Helper to generate prefix based on stack
    def get_prefix():
        return "".join(["> " for item in stack if item == 'admonition'])

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Check for fence
        # Matches ``` or ~~~
        match = re.match(r'^(\s*)(`{3,}|~{3,})(.*)$', line)
        if match:
            indent = match.group(1)
            fence = match.group(2)
            info = match.group(3).strip()
            
            # Check if it matches ad- syntax
            ad_match = re.match(r'^ad-(\w+)', info)
            
            if ad_match:
                # Starting an Admonition
                ad_type = ad_match.group(1).lower()
                
                # Check for title in next line
                title = None
                if i + 1 < len(lines):
                    next_line = lines[i+1].strip()
                    if next_line.startswith("title:"):
                        title = next_line[6:].strip()
                        i += 1 # Consume title line
                
                if not title:
                    title = ad_type.capitalize()
                
                # Push to stack
                # Current prefix BEFORE pushing this new block
                current_prefix = get_prefix()
                
                # Output the Callout Header
                # We typically rely on default indentation for the new blockquote
                # But here we are constructing the markdown string.
                # > [!TYPE] Title
                
                header_line = f"{current_prefix}> [{ad_type.upper()}] {title}"
                output.append(header_line)
                
                stack.append('admonition')
            
            else:
                # Regular code block or closing fence
                # We need to decide if opening or closing.
                # If we are in a code block, this might close it.
                # If we are in an admonition, this might start a code block OR close the admonition?
                
                # Heuristic: 
                # If stack top is 'code', this closes it.
                # If stack top is 'admonition', this closes it.
                # Wait, what if we have nested code/admonition?
                # Usually fences must match (backticks vs tildes, length).
                # For simplicity here: Any fence closes the current top level block 
                # UNLESS it clearly opens a new one (has info string and top is not code).
                
                # Actually, standard markdown:
                # If we are in a code block, only a matching fence closes it.
                # If we are NOT in a code block, a fence opens a code block.
                
                # But here we are parsing "ad-blocks". 
                # The ad-blocks logic we defined: ad- starts a block.
                # And we assume generic fences close it?
                
                # Let's track fence complexity? 
                # For this implementation, let's assume balanced ``` for simplicity 
                # as ad- syntax users typically use basic fencing.
                
                if len(stack) > 0:
                    # Closing the current block
                    # We pop.
                    popped = stack.pop()
                    # If it was a code block, we must output the closing fence text.
                    # If it was admonition, we output nothing (blockquote ends implicitly).
                    
                    if popped == 'code':
                        prefix = get_prefix()
                        output.append(f"{prefix}{line}")
                else:
                    # Opening a generic code block (since stack is empty or we decided so)
                    # Wait, if stack is empty, it's just top level code.
                    # If stack has 'admonition', it is a code block INSIDE admonition.
                    
                    # But wait, what if ` ``` ` is used to OPEN a code block?
                    # line: ```python
                    # It has info.
                    
                    if info:
                        # Opening code block
                        stack.append('code')
                        prefix = get_prefix()
                        output.append(f"{prefix}{line}")
                    else:
                        # No info. Could be open or close.
                        # Since we check stack > 0 above, this `else` implies stack is empty.
                        # So it must be opening a block (or syntax error).
                        stack.append('code')
                        output.append(line)

        else:
            # Normal line
            prefix = get_prefix()
            output.append(f"{prefix}{line}")
            
        i += 1

    return '\n'.join(output)

# REVISED LOGIC TO HANDLE NESTING CORRECTLY
# The previous logic was too simple about open/close.
# We need to distinguish Open vs Close.
# A fence is "Open" if it has info string OR if we are not currently in a "code" block?
# For 'admonition' blocks, they are just implicit containers.
# So inside 'admonition', ` ``` ` is EITHER closing the admonition OR opening a code block?
# 
# Ambiguity:
# ```ad-note
# ```
# Is that closing the note? Yes.
# 
# ```ad-note
# ```python
# ...
# ```
# ```
# 
# 1. `ad-note`. Stack: [ad].
# 2. `python`. Stack: [ad, code]. (Because python != empty)
# 3. ` ``` `. Stack: [ad]. (Closes code)
# 4. ` ``` `. Stack: []. (Closes ad)
# 
# This seems correct.
# 
# What if:
# ```ad-note
# ```
# (No info string).
# 1. `ad-note`. Stack: [ad].
# 2. ` ``` `. Stack: []. (Closes ad).
# 
# Logic: 
# If ` ```` (fence):
#    If `ad-`: Open Admonition.
#    Else If `info string present`: Open Code.
#    Else (no info):
#       If Top is `code`: Close Code.
#       Else If Top is `admonition`: Close Admonition.
#       Else: Open Code (Generic code block start).

def parser_v2(content):
    lines = content.split('\n')
    output = []
    stack = [] # list of dict {'type': 'admonition'|'code', 'fence': '```'}

    def get_prefix():
        return "".join(["> " for item in stack if item['type'] == 'admonition'])

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        match = re.match(r'^(\s*)(`{3,}|~{3,})(.*)$', line)
        
        if match:
            # Indent handling? We probably strip original indent for processing logic
            # but might need it for code blocks.
            # For ad-blocks, we ignore original indent.
            
            fence_char = match.group(2)
            info = match.group(3).strip()
            
            ad_match = re.match(r'^ad-(\w+)', info)
            
            if ad_match:
                # Start Admonition
                ad_type = ad_match.group(1).lower()
                title = None
                if i + 1 < len(lines):
                    if lines[i+1].strip().startswith("title:"):
                        title = lines[i+1].strip()[6:].strip()
                        i += 1
                if not title: title = ad_type.capitalize()
                
                prefix = get_prefix()
                output.append(f"{prefix}> [!{ad_type.upper()}] {title}")
                stack.append({'type': 'admonition', 'fence': fence_char})
            
            else:
                # Generic Code Fence
                # Check if we are closing something
                closing = False
                if len(stack) > 0:
                    top = stack[-1]
                    # If top is code, we assume this closes it?
                    # Only if fence matches ideally. But let's be loose.
                    if top['type'] == 'code':
                        closing = True
                    elif top['type'] == 'admonition':
                        # If inside admonition, ` ``` ` closes the admonition UNLESS it has info string?
                        # If info string provided, it starts a code block.
                        if info:
                            closing = False
                        else:
                            closing = True
                
                if closing:
                    top = stack.pop()
                    if top['type'] == 'code':
                        # Output the closing fence for code
                        prefix = get_prefix()
                        output.append(f"{prefix}{line}")
                    # If admonition, output nothing (just end blockquote)
                else:
                    # Opening Code Block
                    stack.append({'type': 'code', 'fence': fence_char})
                    prefix = get_prefix()
                    output.append(f"{prefix}{line}")
        else:
            prefix = get_prefix()
            output.append(f"{prefix}{line}")
        
        i += 1
    
    return '\n'.join(output)


test_content = """
```ad-question

Outer Text

```ad-success
title: Answer
Inner Text
```

End Outer
```
"""

print(parser_v2(test_content))
