import sys
import os
from pathlib import Path

# Add current directory to path so we can import main
sys.path.append(os.getcwd())

try:
    from main import find_image_in_static, STATICS_DIR
except ImportError:
    print("Could not import main. Make sure you are running from the project root.")
    sys.exit(1)

def run_test():
    print("Starting verification test for recursive image search...")
    
    # 1. Setup test environment
    images_dir = STATICS_DIR / "images"
    if not images_dir.exists():
        images_dir.mkdir(parents=True)
        
    sub_dir = images_dir / "subdir_test"
    sub_dir.mkdir(exist_ok=True)
    
    test_image_name = "test_recursive_image.png"
    test_image_path = sub_dir / test_image_name
    
    # Create empty file
    with open(test_image_path, "w") as f:
        f.write("test content")
        
    print(f"Created test image at: {test_image_path}")
    
    # 2. Run the function
    try:
        url = find_image_in_static(test_image_name)
        print(f"Function returned URL: {url}")
        
        # 3. Verify
        # Expected URL should be /static/images/subdir_test/test_recursive_image.png
        # Note: on Windows relative_to might return backslashes, but our function converts to forward slashes.
        expected_url = "/static/images/subdir_test/test_recursive_image.png"
        
        if url == expected_url:
            print("SUCCESS: Image found correctly with proper URL.")
        else:
            print(f"FAILURE: Expected {expected_url}, but got {url}")
            
    except Exception as e:
        print(f"ERROR during test execution: {e}")
        
    finally:
        # 4. Cleanup
        if test_image_path.exists():
            os.remove(test_image_path)
        if sub_dir.exists():
            os.rmdir(sub_dir)
        print("Cleanup complete.")

if __name__ == "__main__":
    run_test()
