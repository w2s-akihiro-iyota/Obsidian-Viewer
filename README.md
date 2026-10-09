# Obsidian Viewer

ObsidianのようなインターフェースでMarkdownファイルをブラウザ閲覧できるWebアプリケーションです。
ローカルのMarkdownファイルを、美しいテーマと便利な機能（全文検索、タグ、コールアウト、リンクカードなど）付きで表示します。

## 特徴

- **Obsidianライクなデザイン**: ダークモード/ライトモード対応の美しいUI
- **ダッシュボード画面**: 草生やしヒートマップ、全体統計、よく使われるタグ、最近更新されたノート一覧など
- **グラフビュー表示**: Obsidian特有のページ間の繋がり（リンク関係）をネットワーク図として可視化
- **ブラウザからの記事編集・作成**: ローカル(localhost)環境からブラウザ上で直接Markdownの保存やリアルタイムプレビューが可能
- **閲覧・共有の利便性向上**:
  - 画像のLightbox（拡大）表示サポート
  - コードブロックのワンクリックコピーボタン
  - OGP・Twitterカード自動生成（共有先でのリッチなプレビュー）
- **リッチなMarkdownレンダリング**:
  - 数式 (KaTeX) / ダイアグラム (Mermaid.js)
  - コールアウト (Admonition) `info`, `important` など
  - リンクカード (CardLink) / タスクリスト
  - Dataviewライクなクエリ処理
- **全文検索 & インデックス管理**: ファイル名と内容のリアルタイム検索
- **ファイル同期**: ローカルの他フォルダからMarkdownや画像を自動/手動で同期
- **レスポンシブ**: PC、タブレット、スマホに対応

## 動作環境

- Windows / Mac / Linux
- Docker Desktop (または Docker Engine + Docker Compose)

## セットアップ手順

### 1. Dockerのインストール

まだインストールしていない場合は、[公式サイト](https://www.docker.com/products/docker-desktop/)からDocker Desktopをダウンロードしてインストールしてください。

### 2. プロジェクトの準備

このフォルダ一式を任意の場所に配置します。
コマンドプロンプト（またはPowerShell、ターミナル）を開き、プロジェクトのフォルダに移動します。

```bash
cd パス/to/Obsidian-Viewer
```

### 3. Obsidian保管庫 (Vault) の連携設定

プロジェクトのフォルダに `docker-compose.override.yml` を作り、Obsidianの保管庫パスをマウント設定に書きます。
このファイルは Git の管理外です。`docker-compose up` のときに `docker-compose.yml` へ自動で上乗せされます。
`docker-compose.yml` を直接書き換えないことで、自分のPCのパスがコミットに混ざりません。

```yaml
# docker-compose.override.yml
services:
  viewer:
    volumes:
      - {ObsidianのVaultパス}:/0_host_pc:ro
```

**例 (Windowsの場合):**
```yaml
      - D:\Documents\Obsidian:/0_host_pc:ro
```
※ブラウザのエディタから Vault へ保存する場合は、`:ro`（読み取り専用）を外してください。
※パスにスペースが含まれる場合は `"` で囲んでください。
※設定後、アプリ内から `/0_host_pc` を通じてファイルを参照・同期できるようになります。

### 4. アプリケーションの起動

以下のコマンドを実行して、コンテナをビルド・起動します。
初回は時間がかかる場合があります。

```bash
docker-compose up -d --build
```

### 5. ブラウザでアクセス

ブラウザを開き、以下のURLにアクセスしてください。
用途によって開くURLが分かれます。

| URL | 見えるもの | 開ける場所 |
|---|---|---|
| http://localhost:8002 | 管理用。すべてのノートと、設定・同期・エディタ・ダッシュボード | このPCからだけ |
| http://localhost:8000 | 公開用。`publish: true` のノートだけ | 外部からも開ける |

管理用ポートは `docker-compose.yml` で `127.0.0.1` にだけ公開しているため、ほかのPCからは開けません。
ホスト側のポート番号（`8002`）は、`docker-compose.yml` の `"127.0.0.1:8002:8001"` の左側で変えられます。

### 6. コンテナの停止

アプリケーションを終了する場合は、以下のコマンドを実行します。

```bash
docker-compose down
```

## 使い方

### ファイルの追加
`content` フォルダの中に、表示したいMarkdown (`.md`) ファイルを配置してください。
サブフォルダを作成して整理することも可能です。
画像ファイルなどは `static` フォルダなどに配置し、Markdownから参照してください。

### Admonition (コールアウト) の書き方

```markdown
'''ad-info
title: タイトル
ここに内容を書きます。
'''
```
※ `info`, `important`, `warning`, `success`, `question` などが使えます。
※ `'''` はバッククォート(`)3つに置き換えてください。

### Frontmatter (メタデータ)
ファイルの先頭にYAML形式でメタデータを記述できます。

```yaml
---
tags: [tag1, tag2]
publish: true
---
```

### 記事の公開設定

Obsidian Viewer は、公開用ポート（`8000`）からアクセスされた場合、Frontmatter に `publish: true` が設定されたファイルのみを表示します。
管理用ポート（`http://localhost:8002`）からのアクセスでは、すべてのファイルが閲覧可能です。
公開ノートの中の Dataview やタグ一覧も、公開用ポートでは公開ノートだけを対象にします。

#### 方法1: Obsidian Linter プラグインで自動付与する（推奨）

Obsidian のコミュニティプラグイン「**Linter**」を使うと、保存時に Frontmatter を自動挿入・管理できます。

1. Obsidian の **設定 > コミュニティプラグイン** から「Linter」をインストールして有効化する
2. Linter の設定画面を開き、**YAML > Default Value for YAML Key** に以下を設定する
   - Key: `publish`
   - Value: `true`
3. これにより、ファイル保存時に `publish: true` が Frontmatter に自動追加される

> **ヒント:** 特定のファイルを非公開にしたい場合は、手動で `publish: false` に変更してください。Linter は既に値がある場合は上書きしません。

#### 方法2: 手動で Frontmatter に記述する

Markdownファイルの先頭に、以下のように記述します。

```yaml
---
publish: true
---
```

`publish: true` のないファイルは、外部からアクセスした際に非公開（403エラー）となります。

### 共有URLの設定

記事ページの「URLをコピー」機能では、デフォルトで今開いているURL（`http://localhost:8002/view/...` など）が生成されます。
外部の人にURLを共有する場合は、**公開URL (Base URL)** を設定することで、コピーされるURLのドメイン部分を置換できます。

#### 設定手順

1. 管理用URL（`http://localhost:8002`）でアプリにアクセスし、サイドバー下の **歯車アイコン** から設定画面を開く
2. **システム > ファイル同期** タブを選択する
3. 「**公開URL (Base URL)**」欄に、外部からアクセス可能なURLを入力する
   - 例: `https://docs.example.com`、`http://{PC名}:8000`（公開用ポートを指定する）
4. 「**設定を保存**」をクリックする

#### 動作例

| 公開URL設定 | コピーされるURL |
|---|---|
| 未設定 | `http://localhost:8002/view/記事名.md` |
| `https://docs.example.com` | `https://docs.example.com/view/記事名.md` |

> **注意:** 公開URLは、ポートフォワーディングやリバースプロキシなどで外部からアクセスできる状態になっている必要があります。本設定はURLのコピー時の置換のみを行い、ネットワーク設定自体は変更しません。
