import yaml
import shutil
import asyncio
from datetime import datetime
from pathlib import Path
from app.config import CONFIG_FILE, CONTENT_DIR, STATICS_DIR
from app.models.sync import SyncConfig
from app.core.indexing import refresh_global_caches

def load_config():
    """設定ファイルを読み込む。存在しない場合はデフォルト値を返す。"""
    if not CONFIG_FILE.exists():
        return SyncConfig()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return SyncConfig(**data)
    except Exception as e:
        print(f"Failed to load config: {e}", flush=True)
        return SyncConfig()

def save_config(config: SyncConfig):
    """設定ファイルを保存する。"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.safe_dump(config.model_dump(), f)
    except Exception as e:
        print(f"Failed to save config: {e}", flush=True)

def perform_sync(config: SyncConfig):
    """ファイル同期を実行する。"""
    print(f"Starting perform_sync. sync_enabled={config.sync_enabled}, content_src={config.content_src}", flush=True)
    if not config.sync_enabled:
        return False, "Sync is disabled in settings"
    
    if not config.content_src:
        return False, "Content source path is not set"

    try:
        # 1. Content Sync
        src_path = Path(config.content_src)
        if not src_path.exists():
            return False, f"Content source directory not found: {src_path}"

        print(f"Cleaning destination: {CONTENT_DIR}", flush=True)
        if CONTENT_DIR.exists():
            for item in CONTENT_DIR.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception as e:
                    print(f"Warning: Could not delete {item}: {e}", flush=True)
        
        print(f"Copying files from {src_path} to {CONTENT_DIR}", flush=True)
        for item in src_path.iterdir():
            dest_item = CONTENT_DIR / item.name
            if item.is_dir():
                shutil.copytree(item, dest_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest_item)

        # 2. Image Sync (Optional)
        if config.images_src:
            img_src_path = Path(config.images_src)
            if img_src_path.exists() and STATICS_DIR.exists():
                print(f"Syncing images from {img_src_path}...", flush=True)
                for item in img_src_path.iterdir():
                    dest_item = STATICS_DIR / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest_item, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest_item)
            else:
                print(f"Skipping image sync (path not found: {img_src_path})", flush=True)
        
        # 3. Finalize
        config.last_sync = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Sync successful at {config.last_sync}", flush=True)
        save_config(config)
        
        # Trigger cache refresh
        refresh_global_caches()
        return True, "Sync completed successfully"

    except Exception as e:
        error_msg = f"Sync failed: {str(e)}"
        print(error_msg, flush=True)
        import traceback
        traceback.print_exc()
        return False, error_msg

background_task_running = False

async def background_sync_loop():
    """バックグラウンド同期ループ。"""
    global background_task_running
    if background_task_running:
        return
    background_task_running = True
    
    print("Background sync loop started.", flush=True)
    while True:
        try:
            config = load_config()
            if config.sync_enabled and config.auto_sync_enabled:
                print("Checking for auto-sync...", flush=True)
                perform_sync(config)
            
            # Wait for interval (minutes to seconds)
            await asyncio.sleep(max(1, config.interval_minutes) * 60)
        except Exception as e:
            print(f"Error in background sync loop: {e}", flush=True)
            await asyncio.sleep(60)
