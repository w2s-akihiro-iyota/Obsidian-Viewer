from main import get_all_files, CONTENT_DIR
import pathlib

files = get_all_files(CONTENT_DIR, CONTENT_DIR)

print(f"Total files: {len(files)}")
print("-" * 20)
for i, f in enumerate(files[:10]):
    print(f"{i+1}. {f['name']} - {f['updated']} (ts: {f['timestamp']})")
