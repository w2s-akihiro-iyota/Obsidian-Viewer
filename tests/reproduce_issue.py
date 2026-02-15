from pathlib import Path
import os
from urllib.parse import quote

# MOCKING THE ENVIRONMENT to match main.py
BASE_DIR = Path(os.getcwd()).resolve()
STATICS_DIR = BASE_DIR / "static"
print(f"STATICS_DIR: {STATICS_DIR}")

def find_image_in_static(filename: str) -> str:
    """
    Search for an image file in static/images and its subdirectories.
    Returns the URL path (e.g. /static/images/sub/img.png).
    """
    images_dir = STATICS_DIR / "images"
    print(f"Searching in: {images_dir}")
    
    if not images_dir.exists():
         print("images_dir does not exist!")
         return f"/static/images/{quote(filename)}"
         
    if (images_dir / filename).exists():
        print("Found directly.")
        return f"/static/images/{quote(filename)}"
        
    try:
        search_name = os.path.basename(filename)
        print(f"Recursive search for: {search_name}")
        
        # DEBUG: List all files seen by rglob
        # for f in images_dir.rglob("*"):
        #     print(f"  - {f.name}")
            
        found_file = next(images_dir.rglob(search_name))
        print(f"Found file: {found_file}")
        
        parts = found_file.relative_to(STATICS_DIR).parts
        encoded_parts = [quote(p) for p in parts]
        return "/static/" + "/".join(encoded_parts)
    except StopIteration:
        print("StopIteration: File not found in recursive search.")
        return f"/static/images/{quote(filename)}"

if __name__ == "__main__":
    filename = "sample-image.png"
    url = find_image_in_static(filename)
    print(f"Result URL: {url}")
