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

def perform_sync(config: SyncConfig) -> tuple[bool, str]:
    """ファイルの同期を実行します。"""
    logger.info("Starting sync. sync_enabled=%s, content_src=%s", config.sync_enabled, config.content_src)
    if not config.sync_enabled:
        return False, get_system("S104")

    if not config.content_src:
        return False, get_error("E001")

    try:
        # 1. コンテンツの同期
        src_path = Path(config.content_src)
        if not src_path.exists():
            return False, get_error("E002")

        logger.info("Cleaning destination: %s", CONTENT_DIR)
        if CONTENT_DIR.exists():
            for item in CONTENT_DIR.iterdir():
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

        logger.info("Copying files from %s to %s", src_path, CONTENT_DIR)
        for item in src_path.iterdir():
            dest_item = CONTENT_DIR / item.name
            if item.is_dir():
                shutil.copytree(item, dest_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest_item)

        # 2. 画像の同期（オプション）
        if config.images_src:
            img_src_path = Path(config.images_src)
            if img_src_path.exists() and IMAGES_DIR.exists():
                logger.info(get_system("S105"))
                for item in img_src_path.iterdir():
                    dest_item = IMAGES_DIR / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest_item, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest_item)
            else:
                logger.info("Skipping image sync (path not found)")

        # 3. 完了処理
        JST = timezone(timedelta(hours=9))
        config.last_sync = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        logger.info("Sync successful at %s", config.last_sync)
        save_config(config)

        # キャッシュリフレッシュのトリガー
        refresh_global_caches()
        return True, get_system("S102")

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
