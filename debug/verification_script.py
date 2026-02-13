from main import process_obsidian_images, find_image_in_static, STATICS_DIR
import os

# Ensure we are searching in the right place
print(f"STATICS_DIR in main: {STATICS_DIR}")

text = "Here is an image: ![[sample-image.png]]"
result = process_obsidian_images(text)

print(f"Original: {text}")
print(f"Processed: {result}")

# Check if file exists where we think it is
real_path = STATICS_DIR / "images" / "samples" / "sample-image.png"
print(f"File check: {real_path} exists? {real_path.exists()}")
