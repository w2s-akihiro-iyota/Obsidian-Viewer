import os
import re
from pathlib import Path
from app.config import STATICS_DIR
from app import cache

def find_image_in_static(filename: str):
    if filename in cache.IMAGE_PATH_CACHE:
        return cache.IMAGE_PATH_CACHE[filename]
    
    # Check if filename has extension
    has_ext = '.' in filename and filename.split('.')[-1].lower() in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp']
    
    for root, dirs, files in os.walk(STATICS_DIR):
        # Precise match
        if filename in files:
            full_path = Path(root) / filename
            rel_path = full_path.relative_to(STATICS_DIR)
            rel_path_str = str(rel_path).replace('\\', '/')
            url = f"/static/{rel_path_str}"
            cache.IMAGE_PATH_CACHE[filename] = url
            return url
        
        # Ambiguous match (if no extension provided in link)
        if not has_ext:
            for f in files:
                if f.lower().startswith(filename.lower() + '.'):
                    full_path = Path(root) / f
                    rel_path = full_path.relative_to(STATICS_DIR)
                    rel_path_str = str(rel_path).replace('\\', '/')
                    url = f"/static/{rel_path_str}"
                    cache.IMAGE_PATH_CACHE[filename] = url
                    return url
                    
    return None

def process_obsidian_images(content: str):
    def replace_image(match):
        full_match = match.group(0)
        filename = match.group(1).strip()
        size = match.group(2) # |300 or |300x200
        
        # Check if it's an image link ![[...]] or just internal link [[...]]
        is_image_link = full_match.startswith('!')
        
        if is_image_link:
            image_url = find_image_in_static(filename)
            if image_url:
                style = ""
                if size:
                    size_val = size # size already has | stripped by regex group
                    if 'x' in size_val:
                        w, h = size_val.split('x', 1)
                        style = f'width="{w}" height="{h}"'
                    else:
                        style = f'width="{size_val}"'
                
                return f'<img src="{image_url}" alt="{filename}" {style} class="obsidian-image">'
        
        return full_match # fallback

    # Matches ![[image.png|300]] or ![[image|300]] or [[image.png]]
    # Group 1: Path/Filename, Group 2: Size/Alias
    return re.sub(r'!?\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', replace_image, content, flags=re.IGNORECASE)
