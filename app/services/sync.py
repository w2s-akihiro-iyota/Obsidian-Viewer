import yaml
import shutil
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from app.config import CONFIG_FILE, CONTENT_DIR, STATICS_DIR, IMAGES_DIR, PROTECTED_ITEMS
from app.models.sync import SyncConfig
from app.core.indexing import refresh_global_caches
from app.events import config_updated_event

from app.utils.messages import get_system, get_error

logger = logging.getLogger("app.sync")

def load_config() -> SyncConfig:
    """設定ファイルを読み込みます。存在しない場合はデフォルトを作成します。"""
    if not CONFIG_FILE.exists():
        logger.info("Config file not found at %s. Creating default.", CONFIG_FILE)
        # 例からコピー（存在する場合）
        example_file = Path(CONFIG_FILE).parent.parent / "server_config.yaml.example"
        if example_file.exists():
            try:
                shutil.copy2(example_file, CONFIG_FILE)
            except Exception as e:
                logger.error("Failed to copy example config: %s", e)
                save_config(SyncConfig())
        else:
            save_config(SyncConfig())

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return SyncConfig(**data)
    except Exception as e:
        logger.error("Failed to load config: %s", e)
        return SyncConfig()

def save_config(config: SyncConfig) -> None:
    """設定をファイルに保存します。"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.safe_dump(config.model_dump(), f)
    except Exception as e:
        logger.error("Failed to save config: %s", e)

def sync_directory(src_dir: Path, dest_dir: Path, last_sync_timestamp: float | None, is_content: bool = False) -> int:
    """ディレクトリを同期し、同期されたファイル数を返します。"""
    sync_count = 0
    if not last_sync_timestamp:
        if is_content:
            logger.info("Cleaning destination: %s", dest_dir)
            if dest_dir.exists():
                for item in dest_dir.iterdir():
                    if item.name in PROTECTED_ITEMS:
                        logger.debug("Skipping protected item: %s", item.name)
                        continue
                    try:
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                    except Exception as e:
                        logger.warning("Could not delete %s: %s", item, e)

        logger.info("Copying files from %s to %s", src_dir, dest_dir)
        for item in src_dir.iterdir():
            dest_item = dest_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest_item)
        
        sync_count = sum(1 for f in src_dir.rglob('*') if f.is_file())
    else:
        logger.info("Differentially copying files from %s to %s", src_dir, dest_dir)
        for item in src_dir.rglob('*'):
            if item.is_file():
                if item.stat().st_mtime > last_sync_timestamp:
                    rel_path = item.relative_to(src_dir)
                    dest_file = dest_dir / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest_file)
                    sync_count += 1
    return sync_count

def perform_sync(config: SyncConfig) -> tuple[bool, str]:
    """ファイルの同期を実行します。"""
    logger.info("Starting sync. sync_enabled=%s, content_src=%s", config.sync_enabled, config.content_src)
    if not config.sync_enabled:
        return False, get_system("S104")

    if not config.content_src:
        return False, get_error("E001")

    try:
        JST = timezone(timedelta(hours=9))
        
        # 最終同期日時のパース
        last_sync_timestamp = None
        if config.last_sync:
            try:
                last_sync_dt = datetime.strptime(config.last_sync, "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
                last_sync_timestamp = last_sync_dt.timestamp()
            except ValueError:
                logger.warning("Invalid last_sync format: %s. Performing full sync.", config.last_sync)

        # 1. コンテンツの同期
        src_path = Path(config.content_src)
        if not src_path.exists():
            return False, get_error("E002")

        note_count = sync_directory(src_path, CONTENT_DIR, last_sync_timestamp, is_content=True)

        # 2. 画像の同期（オプション）
        image_count = 0
        if config.images_src:
            img_src_path = Path(config.images_src)
            if img_src_path.exists() and IMAGES_DIR.exists():
                logger.info(get_system("S105"))
                image_count = sync_directory(img_src_path, IMAGES_DIR, last_sync_timestamp, is_content=False)
            else:
                logger.info("Skipping image sync (path not found)")

        # 3. 完了処理
        config.last_sync = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        logger.info("Sync successful at %s", config.last_sync)
        save_config(config)

        # キャッシュリフレッシュのトリガー
        refresh_global_caches()
        
        success_msg = f"ノート{note_count}件、画像ファイル{image_count}件を同期しました。"
        return True, success_msg

    except Exception as e:
        error_msg = f"{get_system('S103')}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg

background_task_running = False

async def background_sync_loop() -> None:
    """バックグラウンド同期ループ。"""
    global background_task_running
    if background_task_running:
        return
    background_task_running = True

    logger.info("Background sync loop started")
    while True:
        try:
            config = load_config()
            if config.sync_enabled and config.auto_sync_enabled:
                logger.info("Auto-sync triggered")
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, perform_sync, config)

            wait_time = (config.interval_minutes * 60) if config.auto_sync_enabled else None

            try:
                await asyncio.wait_for(config_updated_event.wait(), timeout=wait_time)
                logger.info("Config updated signal received. Restarting loop.")
            except asyncio.TimeoutError:
                pass
            finally:
                config_updated_event.clear()

        except Exception as e:
            logger.error("Error in background sync loop: %s", e)
            await asyncio.sleep(60)
