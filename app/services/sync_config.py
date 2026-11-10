"""同期の設定ファイル（server_config.yaml）の読み書き

索引の作り直し（app/core/indexing.py）も設定を読むため、同期本体（sync.py。indexing を import する）から分けている。
"""
import logging
import shutil
from pathlib import Path

import yaml

from app.config import CONFIG_FILE
from app.models.sync import SyncConfig

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
