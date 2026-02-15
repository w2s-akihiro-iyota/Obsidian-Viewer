
import re

def process_admonition_blocks_aggressive(content: str) -> str:
    lines = content.split('\n')
    output = []
    # stack of dict {'type': 'admonition'|'code', 'fence': '```', 'len': 3, 'indent': 0}
    stack = [] 

    def get_prefix():
        return "".join(["> " for item in stack if item['type'] == 'admonition'])

    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r'^(\s*)(`{3,}|~{3,})(.*)$', line)
        
        if match:
            indent_str = match.group(1)
            indent_len = len(indent_str.replace('\t', '    '))
            fence_char = match.group(2)
            fence_len = len(fence_char)
            info = match.group(3).strip()
            
            ad_match = re.match(r'^ad-(\w+)', info)
            
            if ad_match:
                # Start Admonition
                ad_type = ad_match.group(1).lower()
                title = None
                if i + 1 < len(lines):
                    next_line_stripped = lines[i+1].strip()
                    if next_line_stripped.startswith("title:"):
                        title = next_line_stripped[6:].strip()
                        i += 1
                if not title: title = ad_type.capitalize()
                
                prefix = get_prefix()
                output.append(f"{prefix}> [!{ad_type.upper()}] {title}")
                stack.append({
                    'type': 'admonition', 
                    'fence': fence_char[0], 
                    'len': fence_len, 
                    'indent': indent_len
                })
            
            else:
                # Generic Code Fence (Open or Close)
                # Determine if this fence closes the stack top(s)
                
                # We need to perform "Aggressive Closing"
                # Keep popping as long as the fence matches the top item
                
                any_closed = False
                
                while len(stack) > 0:
                    top = stack[-1]
                    
                    # Match logic:
                    # 1. Fence Char must match (backtick vs tilde)
                    # 2. Fence Len must be >= Top Fence Len
                    # 3. Indent? 
                    #    - If Top is Code: Indent usually strictly < 4 spaces? 
                    #    - If Top is Admonition: We enforce strict indent equality for this aggression feature?
                    #      Or allow loose match?
                    #    Let's try STRICT indent equality for now to be safe.
                    
                    matches = False
                    if (top['fence'] == fence_char[0] and 
                        fence_len >= top['len']):
                        
                        # Indent check
                        # If matches 0 indent == 0 indent -> Close.
                        if indent_len == top['indent']:
                            matches = True
                        else:
                            # If indentation differs, we stop aggressive closing?
                            # e.g. Outer(0), Inner(4). Fence(4) closes Inner(4). 
                            # Next top is Outer(0). Fence(4) != Outer(0). Stop. Correct.
                            # Fence(0) closes Inner(4)? No. 
                            # But wait, usually Outer(0) fence can close Inner(4) if it's "super closing"?
                            # No, standard markdown doesn't allow outer fence to close inner block unless inner is auto-closed?
                            # But we want to support User's "implied close".
                            
                            # User's case: Inner(0), Outer(0). Fence(0).
                            # Closes Inner(0). Next Outer(0). Matches. Closes Outer(0).
                            pass

                    if matches:
                        # Close it
                        popped = stack.pop()
                        any_closed = True
                        
                        if popped['type'] == 'code':
                            # Output closing fence for code
                            # Note: Only output it ONCE? or for each?
                            # If we had [Ad(0), Code(0)], and Fence(0).
                            # Closes Code(0). Output ```.
                            # Next Ad(0). Matches. Closes Ad. Output nothing.
                            # Correct.
                            prefix = get_prefix() # Calculated AFTER pop for Admonition, but BEFORE for Code?
                            # Wait, get_prefix depends on stack.
                            # If we just popped Code, stack is [Ad]. Prefix is >.
                            # Output: > ```. Correct.
                            
                            # But if popped Admonition. Stack is []. Prefix is empty.
                            # Output nothing. Correct.
                            
                            current_prefix = get_prefix()
                            output.append(f"{current_prefix}{line}")
                            
                        # Continue loop to see if we close more
                    else:
                        break
                
                if not any_closed:
                    # If we didn't close anything, it must be opening a code block
                    stack.append({
                        'type': 'code', 
                        'fence': fence_char[0], 
                        'len': fence_len, 
                        'indent': indent_len
                    })
                    prefix = get_prefix()
                    output.append(f"{prefix}{line}")

        else:
            # Normal line
            prefix = get_prefix()
            output.append(f"{prefix}{line}")
        
        i += 1

    return '\n'.join(output)

# Test Case 1: User's Scenario (0-indent nesting, 1 closer)
content_user = """
```ad-question
Outer
```ad-success
Inner
```
Trailing
"""

# Test Case 2: Indented Step-Out (2-indent inner, 1 closer for inner)
content_stepout = """
```ad-question
  ```ad-success
  Inner
  ```
Outer
```
"""

print("--- USER CASE ---")
print(process_admonition_blocks_aggressive(content_user))
print("\n--- STEPOUT CASE ---")
print(process_admonition_blocks_aggressive(content_stepout))
