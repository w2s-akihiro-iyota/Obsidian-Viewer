from main import get_all_files, CONTENT_DIR
import pathlib

files = get_all_files(CONTENT_DIR, CONTENT_DIR)

targets = ["168_Uny.md", "2024-02-13_勉強会.md", "test_card.md"]

print(f"Total files: {len(files)}")
print("-" * 20)

for t in targets:
    found = next((f for f in files if f['name'] == t), None)
    if found:
        print(f"File: {found['name']}")
        print(f"  Updated: {found['updated']}")
        print(f"  Timestamp: {found['timestamp']}")
    else:
        print(f"File: {t} not found")
