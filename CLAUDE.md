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
│   ├── media.py           # Vault の添付の配信（/media。外部には公開ノートが参照するものだけ）
│   ├── routes.py          # トップレベル・その他ルーティング
│   └── sync.py            # ファイル同期・設定管理API
├── core/
│   ├── dataview.py        # Obsidian Dataviewライクなクエリ処理
│   ├── graph.py           # グラフ（全体・ローカル）の組み立て。外部向けは公開ノートだけで作る
│   ├── heatmap.py         # ダッシュボードのヒートマップ（最終更新日の分布）
│   ├── indexing.py        # ファイルインデックス作成・ツリー構築（scan_notes で各ノートを 1 回だけ読む）
│   ├── markdown.py        # Markdownレンダリング・カスタムプラグイン
│   ├── note_health.py     # ダッシュボードの「手入れが必要なノート」（リンク切れ・孤立・タグなし）
│   ├── note_list.py       # ノート一覧の条件（ListQuery）・絞り込み・並び替え・タグ集計
│   ├── search.py          # 全文検索ロジック
│   └── sync_history.py    # 同期の記録（直近の結果を app/sync_history.json に残す）
├── models/sync.py         # Request/Response用Pydanticモデル
├── services/
│   ├── sync.py            # 物理ファイル同期・バックグラウンドタスク処理
│   ├── note_editing.py    # 既存ノートの編集（Vault を正とした読み書き・衝突検知）
│   ├── images.py          # 画像・メディアファイルの解決（添付の索引 MediaIndex・/media の URL）
│   ├── media_access.py    # 添付を外部に見せてよいかの判定（公開ノートの参照から許可リストを作る）
│   └── media_migration.py # 起動時に static/images の添付を media/ へ移す
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
media/                     # Vault の添付の同期先（/media で配信。同梱サンプルの _viewer-samples/ だけ Git 管理）
static/
├── css/style.css          # メインCSS (変数を多用したテーマ管理)
├── images/                # アプリの部品（logo.png・samples/ のヘルプ画像）だけ。Vault の添付は置かない
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
- Vault の添付は `media/` に置き `/media/{path}`（`app/api/media.py`）で配信する。`/static` はだれにでも配信されるので添付を置かない
  - 管理者は全部。外部の人は同梱サンプル（`media/_viewer-samples/`）と、公開ノートが参照する添付（`cache.PUBLIC_MEDIA_PATHS`。`refresh_global_caches()` で作る）だけ。それ以外は 404（403 にしない＝存在を知らせない）
  - `MEDIA_DIR` の外（`..`・絶対パス・外を指すシンボリックリンク）は `resolve()` して弾く
  - 応答には必ず `X-Content-Type-Options: nosniff` と `Content-Security-Policy: sandbox` を付ける。画像（`MEDIA_INLINE_EXTS`）以外は `Content-Disposition: attachment`（Vault の HTML・SVG でスクリプトを動かさない）
  - 索引の作り直しに失敗したら許可リストを空にする（fail-closed）
- `MARKDOWN_CACHE` のキーは `(path, published_only)`。閲覧者の種類で Dataview の結果が変わるため、共有しない
- パストラバーサル防止: `..` や `/` で始まるパスを拒否
- ファイル読み込みは必ず `CONTENT_DIR` 配下に制限

## Caching Strategy
- 3層のグローバルキャッシュ: `GLOBAL_FILE_CACHE`, `GLOBAL_FILE_TREE_CACHE`, `GLOBAL_FILE_TREE_CACHE_PUBLIC`
- Markdownキャッシュ: ファイルのmtimeで変更検知、変更があれば再レンダリング
- 添付の索引: `MEDIA_INDEX`（名前 → `media/` からの相対パス）。索引の作り直しで 1 回だけ走査し、描画では全走査しない
- 索引の作り直しでは `scan_notes()` で各ノートを 1 回だけ読み、一覧・ツリー・リンクの表・添付の許可リストを全部そこから作る
- 記事ページの描画キャッシュには、公開チェックと OGP に要るもの（本文・description・画像の元）も入れ、表示のたびに読み直さない
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
- Vault の添付: `/app/media/`（`./media` をマウント）
- 設定ファイル: `/app/app/server_config.yaml` (gitignore対象)
- ホストPC Vault: `/0_host_pc:ro` (読み取り専用マウント)

### Files NOT Tracked in Git
- `docker-compose.override.yml` - ホスト固有のVaultパスを書く（`docker-compose.yml` は共通設定として Git 管理する。個人のパスを書かない）
- `app/server_config.yaml` - ランタイム設定
- `content/*` - Markdownコンテンツ (samples/除く)
- `media/*` - Vault の添付 (_viewer-samples/除く)
- `static/images/*` - logo.png と samples/ 以外（アプリの部品だけを置く）

## Testing
- `pytest`（`requirements-dev.txt`）。本番イメージには入れない
- 実行: `docker cp tests/. obsidian-viewer-app:/app/tests/` → `docker exec -w /app -e PYTHONPATH=/app obsidian-viewer-app python -m pytest tests -q`（コンテナに pytest が無ければ先に `pip install pytest`）
- `tests/test_note_editing.py` が既存ノート編集の契約テスト。`tests/` と `debug/` にはほかに手動検証スクリプトもある

## Common Pitfalls
- Uvicornのワーカー数は1に固定すること (ログ重複防止)。起動は `python -m app.server`（2ポートを1プロセスで待ち受け）
- 同期処理で `content/samples/` と `media/_viewer-samples/` は削除しないこと
- タイムゾーンはJST (`UTC+9`) で統一すること
- `messages.yaml` の新規メッセージ追加時は既存のIDパターンに従うこと
