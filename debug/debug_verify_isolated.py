from pathlib import Path
from urllib.parse import quote
import os
import shutil

# Mock setup
BASE_DIR = Path(__file__).resolve().parent
STATICS_DIR = BASE_DIR / "static"
IMAGES_DIR = STATICS_DIR / "images"

def find_image_in_static(filename: str) -> str:
    """
    Search for an image file in static/images and its subdirectories.
    Returns the URL path (e.g. /static/images/sub/img.png).
    """
    if not IMAGES_DIR.exists():
         return f"/static/images/{quote(filename)}"
         
    # 1. Check direct existence (optimization)
    if (IMAGES_DIR / filename).exists():
        return f"/static/images/{quote(filename)}"
        
    # 2. Recursive search
    try:
        search_name = os.path.basename(filename)
        found_file = next(IMAGES_DIR.rglob(search_name))
        
        parts = found_file.relative_to(STATICS_DIR).parts
        encoded_parts = [quote(p) for p in parts]
        return "/static/" + "/".join(encoded_parts)
    except StopIteration:
        return f"/static/images/{quote(filename)}"

# Test
if __name__ == "__main__":
    test_subdir = IMAGES_DIR / "sub_test_dir"
    
    try:
        if not IMAGES_DIR.exists():
            IMAGES_DIR.mkdir(parents=True)
            
        test_subdir.mkdir(exist_ok=True)
        (test_subdir / "test_img.png").touch()
        
        print("Running test logic...")
        url = find_image_in_static("test_img.png")
        print(f"Result URL: {url}")
        
        expected_part = "sub_test_dir/test_img.png"
        if expected_part in url:
            print("SUCCESS: Found recursive image path.")
        else:
            print(f"FAILURE: Expected path containing {expected_part}, got {url}")
            
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        if test_subdir.exists():
            shutil.rmtree(test_subdir)
