from pathlib import Path
import os

# Base directory (Obsidian-Viewer root)
BASE_DIR = Path(__file__).resolve().parent.parent

# Content and Statics directories
CONTENT_DIR = BASE_DIR / "content"
STATICS_DIR = BASE_DIR / "static"
IMAGES_DIR = STATICS_DIR / "images"
TEMPLATES_DIR = BASE_DIR / "templates"

# Cache files
METADATA_CACHE_FILE = BASE_DIR / "metadata_cache.json"
CONFIG_FILE = BASE_DIR / "server_config.yaml"

# Ensure directories exist
for d in [CONTENT_DIR, STATICS_DIR, IMAGES_DIR, TEMPLATES_DIR]:
    if not d.exists():
        d.mkdir(parents=True)
