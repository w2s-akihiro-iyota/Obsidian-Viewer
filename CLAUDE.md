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
├── api/                   # APIルーター/ビューハンドラ
│   ├── content.py         # Markdown記事表示・目次・ファイル操作API
│   ├── dashboard.py       # ダッシュボード用API
│   ├── editor.py          # ブラウザ上の簡易エディタ向けAPI
│   ├── graph.py           # グラフビューAPI
│   ├── routes.py          # トップレベル・その他ルーティング
│   └── sync.py            # ファイル同期・設定管理API
├── core/
│   ├── dataview.py        # Obsidian Dataviewライクなクエリ処理
│   ├── indexing.py        # ファイルインデックス作成・ツリー構築
│   ├── markdown.py        # Markdownレンダリング・カスタムプラグイン
│   └── search.py          # 全文検索ロジック
├── models/sync.py         # Request/Response用Pydanticモデル
├── services/
│   ├── sync.py            # 物理ファイル同期・バックグラウンドタスク処理
│   └── images.py          # 画像・メディアファイルの解決
├── utils/
│   ├── helpers.py         # 管理者判定・CSRF判定等のユーティリティ
│   └── messages.py        # i18nメッセージリーダー
├── cache.py               # インメモリキャッシュのインスタンス管理
├── config.py              # アプリケーションのパス・定数設定
├── events.py              # バックグラウンド処理用のイベント管理
├── logging_config.py      # 標準ロガーのフォーマット等設定
├── main.py                # FastAPIアプリの初期化ポイント（CSRF ミドルウェア）
├── server.py              # 公開用・管理用の 2 ポートを 1 プロセスで起動する
├── server_config.yaml     # ランタイム動的設定
└── messages.yaml          # システム・エラーメッセージ定義

templates/                 # Jinja2ベーステンプレート群
static/
├── css/style.css          # メインCSS (変数を多用したテーマ管理)
└── js/
    ├── script.js          # メインローダー
    └── modules/           # 各機能のES6 Vanilla JSモジュール郡
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
- JSコードは ES6 モジュール(`static/js/modules/`) に機能ごとに分割して管理
- テーマは CSS Custom Properties (`--variable`) で切り替え
- 状態管理は `localStorage` (テーマ、サイドバー状態、サイドバー幅)
- アイコンは Lucide SVG を使用

### HTML (Jinja2 Templates)
- base.html をベースレイアウトとして継承
- テンプレートは `templates/` ディレクトリに配置
- HTMX属性 (`hx-get`, `hx-target` 等) で動的コンテンツを実現

## Security Rules
- 公開用ポート（8000）と管理用ポート（コンテナ内 8001 / ホストの `127.0.0.1:8002`）を 1 プロセスで待ち受ける（`app/server.py`）
- 管理者判定は `is_admin_request()`：管理用ポートに届き、かつ Host が localhost 系のときだけ管理者。Host ヘッダだけで判定しない（偽装できるため）
- 管理エンドポイント (`/api/sync/*`, `/api/reindex`, `/api/dirs`, `/api/editor/*`, `/dashboard`) は `admin_guard()` / `is_admin_request()` で守り、それ以外は403
- 書き込み系メソッド（POST 等）は、Origin（無ければ Referer）が自サイトと違えば403（CSRF対策。`app/main.py` のミドルウェア）
- 公開用ポートからは `publish: true` のファイルのみ表示。タグ一覧・Dataview・検索・グラフ・バックリンクも公開ノートだけを対象にする
- `MARKDOWN_CACHE` のキーは `(path, published_only)`。閲覧者の種類で Dataview の結果が変わるため、共有しない
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
- Uvicornのワーカー数は1に固定すること (ログ重複防止)。起動は `python -m app.server`（2ポートを1プロセスで待ち受け）
- 同期処理で `content/samples/` と `static/images/samples/` は削除しないこと
- タイムゾーンはJST (`UTC+9`) で統一すること
- `messages.yaml` の新規メッセージ追加時は既存のIDパターンに従うこと
