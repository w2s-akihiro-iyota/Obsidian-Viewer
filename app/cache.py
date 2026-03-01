# In-memory Global Index Cache
GLOBAL_FILE_CACHE = []
GLOBAL_FILE_TREE_CACHE = []
GLOBAL_FILE_TREE_CACHE_PUBLIC = []
IMAGE_PATH_CACHE = {}      # {filename: url}
MARKDOWN_CACHE = {}        # {file_path: {html, title, mtime}}
FILE_NAME_CACHE = {}       # {stem: path} e.g. {"Redis 環境構築手順": "infra/Redis 環境構築手順.md"}
BACKLINK_CACHE = {}        # {target_path: [{title, path}]} 被リンクマップ
FORWARD_LINK_CACHE = {}    # {source_path: [target_path]} リンク先マップ
SEARCH_INDEX = None        # SearchIndex instance (TF-IDF全文検索)
SLUG_TO_PATH = {}          # {slug: relative_path} スラッグ→実パス
PATH_TO_SLUG = {}          # {relative_path: slug} 実パス→スラッグ
