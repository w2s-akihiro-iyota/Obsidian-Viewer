from datetime import timedelta, timezone
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
CONFIG_FILE = BASE_DIR / "app" / "server_config.yaml"

# 待ち受けポート（コンテナ内）
# 管理用ポートはホストの 127.0.0.1 にだけ公開する前提（docker-compose.yml の ports を参照）
PUBLIC_PORT = int(os.environ.get("PUBLIC_PORT", "8000"))
ADMIN_PORT = int(os.environ.get("ADMIN_PORT", "8001"))

# 管理用ポートで受け付ける Host 名（DNS リバインディング対策）
ADMIN_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "[::1]"}

# 画面に出す日時のタイムゾーン（JST）
JST = timezone(timedelta(hours=9))

# Pagination
PER_PAGE = 12

# ノート一覧の上に出すタグの数（件数の多い順）
LIST_TOP_TAG_COUNT = 8

# ダッシュボードのタグ分布に出すタグの数（件数の多い順）
DASHBOARD_TOP_TAG_COUNT = 20

# 検索（/api/search）で返す最大件数
SEARCH_LIMIT = 20

# 読了時間の算出基準（日本語: 500文字/分）
READING_SPEED_JP = 500

# 同期時に削除しない保護対象（コピー先の直下の名前で判定）
PROTECTED_ITEMS = ["samples", "demo.md", ".git", ".gitignore"]
PROTECTED_IMAGE_ITEMS = PROTECTED_ITEMS + ["logo.png"]

# 1回の同期でこの割合以上のファイルが消える場合は、削除を保留して確認を待つ
SYNC_DELETE_HOLD_RATIO = 0.5

# ノートの埋め込み（![[ノート]]）の入れ子の上限。これより深いものは埋め込まずにリンクにする
MAX_EMBED_DEPTH = 2

# Ensure directories exist
for d in [CONTENT_DIR, STATICS_DIR, IMAGES_DIR, TEMPLATES_DIR]:
    if not d.exists():
        d.mkdir(parents=True)
