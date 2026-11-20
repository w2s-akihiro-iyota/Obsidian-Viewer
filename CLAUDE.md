# Obsidian Viewer - Project Rules

## Project Overview
ObsidianライクなインターフェースでMarkdownファイルをブラウザ閲覧するWebアプリケーション。
Docker上で動作し、FastAPI + Jinja2 + HTMX で構成される。

## Tech Stack
- **Backend**: Python 3.11, FastAPI, Uvicorn, Jinja2
- **Frontend**: Vanilla JS, HTMX (1.9.10), CSS Custom Properties
- **Markdown**: markdown-it-py + カスタムプラグイン (callout, cardlink, mark)
- **Client Libraries**: Mermaid.js (11.17.2), KaTeX (0.16.9), Highlight.js (11.9.0), d3 (7.9.0)。すべてローカル配信（`static/js/vendor/<lib>-<version>/` に版を固定して Git 管理。CDN・Web フォントは使わない。Highlight.js だけは `static/js/vendor/highlight.min.js`、テーマは `static/css/themes/`）
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
│   ├── html_sanitizer.py  # 描いた HTML を許可リストで組み直す（sanitize_html。render_markdown の最後でかける）
│   ├── indexing.py        # ファイルインデックス作成・ツリー構築（scan_notes で各ノートを 1 回だけ読む）
│   ├── markdown.py        # Markdownレンダリング・カスタムプラグイン
│   ├── note_health.py     # ダッシュボードの「手入れが必要なノート」（リンク切れ・孤立・タグなし）
│   ├── note_list.py       # ノート一覧の条件（ListQuery）・絞り込み・並び替え・タグ集計
│   ├── search.py          # 全文検索ロジック
│   └── sync_history.py    # 同期の記録（直近の結果を app/sync_history.json に残す）
├── models/sync.py         # Request/Response用Pydanticモデル
├── services/
│   ├── sync.py            # 物理ファイル同期・バックグラウンドタスク処理
│   ├── sync_config.py     # 同期の設定ファイル（server_config.yaml）の読み書き
│   ├── sync_pending.py    # 同期で保留した削除（確認待ち）の置き場。設定画面の一覧・件数はここから読む
│   ├── note_editing.py    # 既存ノートの編集（Vault を正とした読み書き・衝突検知）
│   ├── images.py          # 画像・メディアファイルの解決（添付の索引 MediaIndex・/media の URL）
│   ├── media_access.py    # 添付を外部に見せてよいかの判定（公開ノートの参照から許可リストを作る）
│   └── media_migration.py # 起動時に static/images の添付を media/ へ移す
├── utils/
│   ├── helpers.py         # 管理者判定・CSRF判定等のユーティリティ
│   ├── messages.py        # i18nメッセージリーダー
│   └── static_version.py  # CSS・JS の URL に中身から作った版（?v=）を付ける（テンプレートの static_url / stylesheet_urls）。版付きの URL の配信（VersionedStaticFiles）
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
├── css/style.css          # 読み込む CSS（modules/）の順の一覧。ページはこの順に 1 つずつ <link> で読み込む
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
  - アクセント色は用途で使い分ける: 線・地・飾りは `--accent-purple`、文字は `--accent-text`、白い文字を載せる塗りは `--accent-fill`（どれもテーマごとの値は `variables.css`）。色を直書きしない
- テンプレートから CSS・JS を読み込むときは `{{ static_url("js/modules/x.js") }}` を使う。版（`?v=`）は中身から自動で付くので、手で書かない。CSS を足すときは `static/css/style.css` に `@import` を足す
  - 版は起動して最初に使ったときに作り、再起動まで変えない（ページのたびにファイルを見に行くと、Docker のマウント越しで 1 秒以上かかるため）。CSS・JS を直したら再起動する（下の Build & Run）
  - 版付きの URL はブラウザが 1 年覚える（`Cache-Control: immutable`。`app/utils/static_version.py` の `VersionedStaticFiles`）。版の付かない URL（vendor・logo など）には付けない
- 状態管理は `localStorage` (テーマ、サイドバー状態、サイドバー幅、サイドバーのタブと閲覧履歴、全体グラフの配置（`graph-render.js` の `layoutKey`。点と線が変わったら計算し直す）)
  - 覚えた状態で見た目が変わるものは、最初の描画の前に反映する。defer の JS・DOMContentLoaded では間に合わない（本文を読み終えたところで描くことがある）ので、後から切り替えるとちらつく
    - `<html>` のクラス・属性で決まるもの（テーマ・サイドバーの開閉など）は `before-paint.js`（head で defer なし）
    - サイドバーのタブと閲覧履歴の一覧は `history.js`（head で defer なし。本文を読みながら MutationObserver で組み立てる）
- アイコンは Lucide SVG を使用
- モーダル（開いているときは `.active`）の一覧は `core.js` の `MODALS_TOP_FIRST` の 1 つだけ。Esc・裏のスクロールの固定・ショートカットを止めるのは、どれもここから決まる
  - モーダルを足したら、`MODALS_TOP_FIRST` に重なりの上からの順で足す（根拠は z-index と、同じ値なら DOM の順。z-index は `variables.css` の `--z-*` を使う）
  - `.active` を付け外ししたら `syncBackgroundScrollLock()` を呼ぶ。Esc は `closeOnEscapeWhenTopmost(modal, close)` で受ける（いちばん上のときだけ閉じる）
  - モーダルの外のキー操作（ショートカット・つながりやツリーの Esc など）は、`isAnyModalOpen()` を見てモーダルに譲る

### HTML (Jinja2 Templates)
- base.html をベースレイアウトとして継承
- テンプレートは `templates/` ディレクトリに配置
- HTMX属性 (`hx-get`, `hx-target` 等) で動的コンテンツを実現
- 閲覧者の種類は、画面を返すルートがすべて `viewer_context()`（`app/utils/helpers.py`）で渡す。管理者向けの操作は `show_admin_ui`（外部の人の表示では False）、ヘルプなどの管理者向けの説明は `is_admin` で出し分ける

## Security Rules
- 公開用ポート（8000）と管理用ポート（コンテナ内 8001 / ホストの `127.0.0.1:8002`）を 1 プロセスで待ち受ける（`app/server.py`）
- 管理者判定は `is_admin_request()`：管理用ポートに届き、かつ Host が localhost 系のときだけ管理者。Host ヘッダだけで判定しない（偽装できるため）
- 管理エンドポイント (`/api/sync/*`, `/api/reindex`, `/api/dirs`, `/api/editor/*`, `/dashboard`) は `admin_guard()` / `is_admin_request()` で守り、それ以外は403
- 書き込み系メソッド（POST 等）は、Origin（無ければ Referer）が自サイトと違えば403（CSRF対策。`app/main.py` のミドルウェア）
- 公開用ポートからは `publish: true` のファイルのみ表示。タグ一覧・Dataview・検索・グラフ・バックリンクも公開ノートだけを対象にする
- Vault の添付は `media/` に置き `/media/{path}`（`app/api/media.py`）で配信する。`/static` はだれにでも配信されるので添付を置かない
  - 管理者は全部。外部の人は同梱サンプル（`media/_viewer-samples/`）と、公開ノートが参照する添付（`cache.PUBLIC_MEDIA_PATHS`。`refresh_global_caches()` で作る）だけ。それ以外は 404（403 にしない＝存在を知らせない）
  - `MEDIA_DIR` の外（`..`・絶対パス・外を指すシンボリックリンク）は `resolve()` して弾く
  - 応答には必ず `X-Content-Type-Options: nosniff` と `Content-Security-Policy: sandbox` を付ける。画像（`MEDIA_INLINE_EXTS`）以外は `Content-Disposition: attachment` と `application/octet-stream`（Vault の HTML・SVG・JS でスクリプトを動かさない。.js がページの CSP の `script-src 'self'` をすり抜けないように）
  - 索引の作り直しに失敗したら許可リストを空にする（fail-closed）
- ノートの HTML（生の HTML を含む）は、`render_markdown()`（`app/services/content.py`）の最後で `sanitize_html()`（`app/core/html_sanitizer.py`）を通す。許可したタグ・属性・CSS のプロパティだけを組み直し、HTML に無いタグは文字で出す
  - 描画のプラグインが新しいタグ・属性・class を出すようにしたら、`_ALLOWED_ATTRS`（「アプリの出力」の見出しの下）に足し、`tests/test_html_sanitizer.py` の `_APP_FEATURES` に記法を足す（足し忘れると、落ちたものを名指しして落ちる）
  - href の scheme は `LINK_SCHEMES`（http・https・mailto・obsidian）だけ。自動リンク（`<scheme:...>`）も同じ定数で決める
- ページ（text/html の応答）には CSP を付ける（`app/config.py` の `CONTENT_SECURITY_POLICY`。`app/main.py` のミドルウェアと、500 のエラー画面は `app/api/errors.py`）
  - テンプレートにインラインの `<script>`・`onclick=` などのイベント属性・`javascript:` を書かない。`static/js/` のファイルにして src で読む（`tests/test_csp.py` が見張る）
  - 先読みのルールは `SPECULATION_RULES_JSON` に置き、CSP はその hash で許す（テンプレートで書き足さない）。HTMX は htmx-config で eval と script タグを切っているので、`hx-trigger` の `[...]` のフィルタ・`hx-on` は使えない
- `MARKDOWN_CACHE` のキーは `(path, published_only)`。閲覧者の種類で Dataview の結果が変わるため、共有しない
- パストラバーサル防止: `..` や `/` で始まるパスを拒否
- ファイル読み込みは必ず `CONTENT_DIR` 配下に制限

## Caching Strategy
- 3層のグローバルキャッシュ: `GLOBAL_FILE_CACHE`, `GLOBAL_FILE_TREE_CACHE`, `GLOBAL_FILE_TREE_CACHE_PUBLIC`
- Markdownキャッシュ: ファイルのmtimeで変更検知、変更があれば再レンダリング
- 添付の索引: `MEDIA_INDEX`（名前 → `media/` からの相対パス）。索引の作り直しで 1 回だけ走査し、描画では全走査しない
- 索引の作り直しでは `scan_notes()` で各ノートを 1 回だけ読み、一覧・ツリー・リンクの表・添付の許可リストを全部そこから作る
- 記事ページの描画キャッシュには、公開チェックと OGP に要るもの（本文・description・画像の元）も入れ、表示のたびに読み直さない
- リンクのグラフ（`LINK_GRAPH`・外部向けの `LINK_GRAPH_PUBLIC`）も索引の作り直しで作り、記事ページのつながりの数と `/api/graph` は `cached_link_graph()` で使う
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
- `app/`・`templates/`・`static/` はマウントしているが、Uvicorn は変更を自動で読み直さない。`app/` の Python か `static/` の CSS・JS を変えたら `docker restart obsidian-viewer-app`（テンプレートは次のリクエストから新しくなる）
  - Python だけ古いままだと、新しいテンプレートが新しい名前を使ったときに全ページが 500 になる。CSS・JS は版が変わらないので、ブラウザが古いものを使い続ける

### Important Paths (Docker Container)
- コンテンツ: `/app/content/`
- 静的ファイル: `/app/static/`
- Vault の添付: `/app/media/`（`./media` をマウント）
- 設定ファイル: `/app/app/server_config.yaml` (gitignore対象)
- ホストPC Vault: `/0_host_pc`（`docker-compose.override.yml` でマウント。読むだけなら `:ro`、ブラウザのエディタから Vault へ保存するなら `:ro` を外す。README の手順 3）

### Files NOT Tracked in Git
- `docker-compose.override.yml` - ホスト固有のVaultパスを書く（`docker-compose.yml` は共通設定として Git 管理する。個人のパスを書かない）
- `app/server_config.yaml` - ランタイム設定
- `content/*` - Markdownコンテンツ (samples/除く)
- `media/*` - Vault の添付 (_viewer-samples/除く)
- `static/images/*` - logo.png と samples/ 以外（アプリの部品だけを置く）
- 上の Git 管理外の物は、Docker イメージにも入れない（`.dockerignore`。テスト・`.git`・AI の作業用ファイルも入れない）

## Testing
- `pytest==9.1.1` と `httpx2==2.13.1`（`requirements-dev.txt`。starlette 1.7 の TestClient が使う）。本番イメージには入れない
- 設定はリポジトリ直下の `pytest.ini`（`testpaths = tests`、`pythonpath = .`）
- 実行: `docker cp tests/. obsidian-viewer-app:/app/tests/` と `docker cp pytest.ini obsidian-viewer-app:/app/` → `docker exec -w /app obsidian-viewer-app python -m pytest -q -p no:cacheprovider`
  - コンテナに pytest・httpx2 が無ければ先に `docker exec obsidian-viewer-app pip install pytest==9.1.1 httpx2==2.13.1`（`requirements-dev.txt` はコンテナにマウントされていないので、版は `requirements-dev.txt` と同じものを直接指定する）
- `/app/app` と `templates/` は compose でマウント済み。`tests/` と `pytest.ini` はイメージに入れない（`.dockerignore`）ので、実行前にコピーする。消したテストはコンテナ側からも消す
- テストは対象モジュールごとのファイルに分ける（例 `tests/test_slug.py`）。`tests/test_api.py` は API・画面の契約テスト、`tests/test_note_editing.py` は既存ノート編集の契約テスト
- `tests/` には `test_*.py` 以外を置かない（手動の検証スクリプトは残さない）。共通の fixture は `tests/conftest.py`
- 索引を作り直すテスト（`refresh_global_caches()`）は、`conftest.py` の `isolated_caches` を使う（`app/cache.py` のキャッシュを全部、終わったら元に戻す。キャッシュを足しても直す所は無い）
- テスト用のノートを置くときは、`conftest.py` の `use_test_vault` を使う。読む側（表示・索引・リンク・編集・添付の配信）の `CONTENT_DIR`・`MEDIA_DIR` の差し替えはここだけに書く（同期と添付の引っ越しのテストは、書き込み先なので自分で差し替える）
- E2E（`tests/test_e2e_*.py`。JS のキー操作・フォーカスの移動・768px をまたいだときの動き）は Playwright の Python 版。pytest-playwright は使わず、fixture は `conftest.py` の `e2e`。2 ファイル以上で使う定数（セレクタ・幅・閲覧者）は `conftest.py` の `E2E_*` を `from conftest import` で使う
  - 入れ方（コンテナを作り直したら入れ直す）: `docker exec obsidian-viewer-app sh -c "apt-get update && apt-get install -y libatomic1"`（Playwright 同梱の Node が使う）→ `pip install playwright==1.65.2`（版は `requirements-dev.txt` と同じ）→ `python -m playwright install --with-deps --only-shell chromium`
  - いつもの全件に入る。skip するのは、入っていないことが確かなとき（playwright のモジュールが無い・Chromium の実行ファイルが無い）だけ。入っているのに読み込めない・起動できない壊れた環境は、理由と入れ方を付けて失敗にする
  - テストの中で、テスト用のノート（`conftest.py` の `E2E_NOTES`）だけを読むサーバーを、127.0.0.1 の空きポートに管理用・公開用の 2 つ立てる（lifespan なし）。本物の 8000・8002 番と content には触らない
  - 設定は本物の `app/server_config.yaml` を読むので、ブラウザからの GET・HEAD 以外（プレビューを除く）は既定で止め、止めたら失敗にする。保存などを確かめるテストは `page.route` で受けて偽の応答を返す（サーバーに届かせない）
  - 直っていない不具合は、直したら通るテストを `xfail(strict=True, raises=AssertionError, reason=...)` で置く
    - reason には、ロードマップの ID と、証拠にする状態（どこで何をすると、何がどうなっているか）を書く
    - 不具合の判定は AssertionError で落ちる書き方にする（`expect`・`assert`・`e2e.wait_until`）。click・wait_for_url などの操作の失敗（Playwright の TimeoutError）は raises に当たらず、xfail に吸われないで失敗になる
    - 不具合の手前の準備は `e2e.precondition()` で囲む（崩れたら xfail で隠さず失敗にする）。判定は囲まない（囲むと今の落ち方まで失敗になり、直ったときの XPASS も出ない）。直し方しだいで変わる状態は、準備ではなく判定の側で見る
    - xfail の印が付いたテストは、`expect` と `wait_until` の上限が 2 秒になる（`e2e` が印を見て自動で切り替える）。直したら印を外して、そのテストを流して通ることを確かめる（待ちが短いままだと、直ったのに xfail のままになることがある）

## Common Pitfalls
- Uvicornのワーカー数は1に固定すること (ログ重複防止)。起動は `python -m app.server`（2ポートを1プロセスで待ち受け）
- 同期処理で `content/samples/` と `media/_viewer-samples/` は削除しないこと
- タイムゾーンはJST (`UTC+9`) で統一すること
- `messages.yaml` の新規メッセージ追加時は既存のIDパターンに従うこと
