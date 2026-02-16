import yaml
import shutil
import asyncio
from datetime import datetime
from pathlib import Path
from app.config import CONFIG_FILE, CONTENT_DIR, STATICS_DIR, IMAGES_DIR
from app.models.sync import SyncConfig
from app.core.indexing import refresh_global_caches
from app.events import config_updated_event

def load_config():
    """設定ファイルを読み込む。存在しない場合はデフォルト値を生成して保存する。"""
    if not CONFIG_FILE.exists():
        print(f"Config file not found at {CONFIG_FILE}. Creating default.", flush=True)
        # テンプレートがあればコピー、なければデフォルトSyncConfigを保存
        example_file = Path(CONFIG_FILE).parent.parent / "server_config.yaml.example"
        if example_file.exists():
            try:
                shutil.copy2(example_file, CONFIG_FILE)
            except Exception as e:
                print(f"Failed to copy example config: {e}", flush=True)
                save_config(SyncConfig())
        else:
            save_config(SyncConfig())
            
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
        PROTECTED_ITEMS = ["samples", "demo.md", ".git", ".gitignore"]
        if CONTENT_DIR.exists():
            for item in CONTENT_DIR.iterdir():
                if item.name in PROTECTED_ITEMS:
                    print(f"Skipping protected item: {item.name}", flush=True)
                    continue
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
        from app.config import IMAGES_DIR
        if config.images_src:
            img_src_path = Path(config.images_src)
            if img_src_path.exists() and IMAGES_DIR.exists():
                print(f"Syncing images from {img_src_path} to {IMAGES_DIR}...", flush=True)
                # Recursive sync for images
                for item in img_src_path.iterdir():
                    dest_item = IMAGES_DIR / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest_item, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest_item)
            else:
                print(f"Skipping image sync (path not found or IMAGES_DIR missing)", flush=True)
        
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
            # 1. 動作条件の確認と実行
            if config.sync_enabled and config.auto_sync_enabled:
                print("Checking for auto-sync (Triggered)...", flush=True)
                # Run sync in a thread to avoid blocking the event loop
                await asyncio.to_thread(perform_sync, config)
            
            # 2. 待機フェーズ
            # 自動同期がOFFの場合は信号が来るまで無限に待機(None)、ONの場合は設定時間待機
            wait_time = (config.interval_minutes * 60) if config.auto_sync_enabled else None
            
            try:
                # 設定変更イベントまたはタイムアウトを待つ
                # wait_for に None を渡すとタイムアウトなし（無限待機）になる
                await asyncio.wait_for(config_updated_event.wait(), timeout=wait_time)
                print("Config updated signal received. Restarting loop.", flush=True)
            except asyncio.TimeoutError:
                # タイムアウト（時間経過）による通常の自動実行へ
                pass
            finally:
                # 次の待機のためにイベントをクリア
                config_updated_event.clear()

        except Exception as e:
            print(f"Error in background sync loop: {e}", flush=True)
            await asyncio.sleep(60)
