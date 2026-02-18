# Obsidian Viewer - Project Rules

## Project Overview
ObsidianライクなインターフェースでMarkdownファイルをブラウザ閲覧するWebアプリケーション。
Docker上で動作し、FastAPI + Jinja2 + HTMX で構成される。

## Tech Stack
- **Backend**: Python 3.11, FastAPI, Uvicorn, Jinja2
- **Frontend**: Vanilla JS, HTMX (1.9.10), CSS Custom Properties
- **Markdown**: markdown-it-py + カスタムプラグイン (callout, cardlink, mark)
- **Client Libraries**: Mermaid.js, KaTeX, Highlight.js (CDN + ローカルフォールバック)
- **Infrastructure**: Docker, Docker Compose
- **Database**: なし (インメモリキャッシュ + ファイルシステム)

## Architecture

```
app/
├── api/routes.py          # 全APIエンドポイント・ビューハンドラ
├── core/
│   ├── markdown.py        # Markdownレンダリング・カスタムプラグイン
│   └── indexing.py        # ファイルインデックス・ツリー構築・キャッシュ
├── models/sync.py         # Pydanticモデル
├── services/
│   ├── sync.py            # ファイル同期・バックグラウンドタスク
│   └── images.py          # Obsidian画像リンク処理
├── utils/
│   ├── helpers.py         # リクエスト検証・localhost判定
│   └── messages.py        # メッセージ/i18n (YAML読み込み)
├── cache.py               # グローバルインメモリキャッシュ定義
├── config.py              # パス定数・ディレクトリ設定
├── events.py              # 非同期イベントシグナル
├── main.py                # FastAPIアプリ初期化
└── messages.yaml          # システムメッセージ定義 (日本語)

templates/                 # Jinja2テンプレート (base.html, index.html, view.html)
static/css/style.css       # メインスタイルシート (4テーマ: dark, light, letter, midnight)
static/js/script.js        # フロントエンドロジック
```

## Coding Conventions

### Python (Backend)
- print文には必ず `flush=True` を付ける (Docker環境でのログ即時出力)
- ファイルパス操作には `pathlib.Path` を使用
- 設定値は `app/config.py` で一元管理
- 非同期処理は `asyncio` + FastAPIの `BackgroundTasks` を使用
- バリデーションには Pydantic `BaseModel` を使用
- エラーハンドリングには FastAPI の `HTTPException` を使用
- エンコーディングは常に `encoding="utf-8"` を明示
- docstringやコメントは日本語で記述

### Frontend (JavaScript/CSS)
- フレームワーク不使用、Vanilla JS で記述
- 動的更新には HTMX を使用 (SPAフレームワークは使わない)
- テーマは CSS Custom Properties (`--variable`) で切り替え
- 状態管理は `localStorage` (テーマ、サイドバー状態、サイドバー幅)
- アイコンは Lucide SVG を使用

### HTML (Jinja2 Templates)
- base.html をベースレイアウトとして継承
- テンプレートは `templates/` ディレクトリに配置
- HTMX属性 (`hx-get`, `hx-target` 等) で動的コンテンツを実現

## Security Rules
- 管理エンドポイント (`/api/sync/*`, `/api/reindex`, `/api/dirs`) はlocalhost限定
- `is_request_local()` でリクエスト元を検証し、外部アクセスは403で拒否
- 非localhostからは `publish: true` のファイルのみ表示
- パストラバーサル防止: `..` や `/` で始まるパスを拒否
- ファイル読み込みは必ず `CONTENT_DIR` 配下に制限

## Caching Strategy
- 3層のグローバルキャッシュ: `GLOBAL_FILE_CACHE`, `GLOBAL_FILE_TREE_CACHE`, `GLOBAL_FILE_TREE_CACHE_PUBLIC`
- Markdownキャッシュ: ファイルのmtimeで変更検知、変更があれば再レンダリング
- 画像パスキャッシュ: `IMAGE_PATH_CACHE` で効率的なリンク解決
- キャッシュ更新は `refresh_global_caches()` で一括実行

## Messages & i18n
- システムメッセージは `app/messages.yaml` に集約
- カテゴリ: errors (E001-E101), warnings (W001-W002), system (S001-S105)
- メッセージ取得: `get_error()`, `get_warning()`, `get_system()` を使用
- UI言語は日本語

## Development

### Build & Run
```bash
docker-compose up -d --build     # ビルド＆起動
docker-compose down              # 停止
docker-compose logs -f           # ログ確認
```

### Important Paths (Docker Container)
- コンテンツ: `/app/content/`
- 静的ファイル: `/app/static/`
- 設定ファイル: `/app/app/server_config.yaml` (gitignore対象)
- ホストPC Vault: `/0_host_pc:ro` (読み取り専用マウント)

### Files NOT Tracked in Git
- `docker-compose.yml` - ホスト固有のVaultパスを含む
- `app/server_config.yaml` - ランタイム設定
- `content/*` - Markdownコンテンツ (samples/除く)
- `static/images/*` - 画像ファイル (samples/除く)

## Testing
- 自動テストフレームワークは未導入
- `tests/` と `debug/` に手動検証スクリプトあり

## Common Pitfalls
- Uvicornのワーカー数は1に固定すること (ログ重複防止)
- 同期処理で `content/samples/` と `static/images/samples/` は削除しないこと
- タイムゾーンはJST (`UTC+9`) で統一すること
- `messages.yaml` の新規メッセージ追加時は既存のIDパターンに従うこと
