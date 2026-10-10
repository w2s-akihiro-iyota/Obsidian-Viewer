from datetime import timedelta, timezone
from pathlib import Path
import os

# Base directory (Obsidian-Viewer root)
BASE_DIR = Path(__file__).resolve().parent.parent

# Content and Statics directories
CONTENT_DIR = BASE_DIR / "content"
STATICS_DIR = BASE_DIR / "static"
# アプリの部品の画像（ロゴ・ヘルプの画像）。/static でだれにでも配信するので、Vault の添付は置かない
APP_IMAGES_DIR = STATICS_DIR / "images"
# Vault の添付（画像など）の置き場。/media で配信し、外部の人には公開ノートが参照するものだけを見せる（S-5）
MEDIA_DIR = BASE_DIR / "media"
TEMPLATES_DIR = BASE_DIR / "templates"

# Cache files
METADATA_CACHE_FILE = BASE_DIR / "metadata_cache.json"
CONFIG_FILE = BASE_DIR / "app" / "server_config.yaml"
# 同期の記録（F-7）。server_config.yaml と同じ場所に、別のファイルとして置く（Git 管理外）
SYNC_HISTORY_FILE = CONFIG_FILE.parent / "sync_history.json"

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

# ダッシュボードの「手入れが必要なノート」の表に出す最大件数（残りは「ほか N 件」）
DASHBOARD_HEALTH_ROW_LIMIT = 50

# ダッシュボードのヒートマップの週数（今週を含めて 53 週。列の数になる）
DASHBOARD_HEATMAP_WEEKS = 53

# ヒートマップの濃さの区切り（その日に更新したノートの文字数の合計）。
# 0 文字は 0、1000 以下は 1、5000 以下は 2、超えれば 3。段数を変えたら dashboard.css の .level-N も合わせる
HEATMAP_LEVEL_LIMITS = (1000, 5000)

# ヒートマップの月のラベルの間がこの列数より狭ければ、前のラベルを出さない（最初の月が数日しか無いときに重ならないように）
HEATMAP_MONTH_LABEL_MIN_GAP = 3

# ダッシュボードの「リンク切れ」の原因の列に出す、リンク先の名前の数（残りは「ほか N 件」）
DASHBOARD_CAUSE_NAME_COUNT = 3

# 記事ページのローカルグラフ（/api/graph?center=）に出す点の最大数。超えた分は中心から遠い点から切る
LOCAL_GRAPH_MAX_NODES = 80

# ローカルグラフで選べる深さ（何歩先まで出すか）。先頭が既定で、ほかの値は既定にする。記事ページの切り替えもこれから作る
LOCAL_GRAPH_DEPTHS = (1, 2)

# 検索（/api/search）で返す最大件数
SEARCH_LIMIT = 20

# 読了時間の算出基準（日本語: 500文字/分）
READING_SPEED_JP = 500

# 同期時に削除しない保護対象（コピー先の直下の名前で判定）
PROTECTED_ITEMS = ["samples", "demo.md", ".git", ".gitignore"]
# アプリ同梱のサンプルの添付を置く MEDIA_DIR 直下のフォルダ名（Git 管理）。
# 外部の人にも参照に関係なく見せるので、Vault の添付フォルダと名前がぶつかりにくい名前にしている
MEDIA_SAMPLES_DIR_NAME = "_viewer-samples"

# 添付の同期（MEDIA_DIR）で削除しない保護対象。同梱のサンプルだけ
PROTECTED_MEDIA_ITEMS = [MEDIA_SAMPLES_DIR_NAME]

# 添付の配信（/media）で、画面に埋め込んで表示する拡張子。これ以外（svg を除く）はダウンロードとして返す
# svg は <img> で表示できるよう inline のまま返す（CSP sandbox と nosniff で、直接開いてもスクリプトを動かさない）
MEDIA_INLINE_EXTS = frozenset({"png", "jpg", "jpeg", "gif", "webp", "avif", "bmp", "ico", "svg"})

# 1回の同期でこの割合以上のファイルが消える場合は、削除を保留して確認を待つ
SYNC_DELETE_HOLD_RATIO = 0.5

# 同期の記録（F-7）に残す回数（新しいものから）
SYNC_HISTORY_LIMIT = 10

# 同期の記録に残すファイル名の上限（1 回・1 種類・追加/更新/削除それぞれ）。超えた分は件数だけ残す
SYNC_HISTORY_FILE_LIMIT = 200

# ノートの埋め込み（![[ノート]]）の入れ子の上限。これより深いものは埋め込まずにリンクにする
MAX_EMBED_DEPTH = 2

# Ensure directories exist
for d in [CONTENT_DIR, STATICS_DIR, APP_IMAGES_DIR, MEDIA_DIR, TEMPLATES_DIR]:
    if not d.exists():
        d.mkdir(parents=True)
