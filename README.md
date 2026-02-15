# Obsidian Viewer

ObsidianのようなインターフェースでMarkdownファイルをブラウザ閲覧できるWebアプリケーションです。
ローカルのMarkdownファイルを、美しいテーマと便利な機能（全文検索、タグ、コールアウト、リンクカードなど）付きで表示します。

## 特徴

- **Obsidianライクなデザイン**: ダークモード/ライトモード対応の美しいUI
- **リッチなMarkdownレンダリング**:
  - 数式 (KaTeX)
  - ダイアグラム (Mermaid.js)
  - コールアウト (Admonition) `info`, `important`, `warning` など
  - リンクカード (CardLink)
  - タスクリスト
- **全文検索 & インデックス管理**: ファイル名と内容のリアルタイム検索、手動インデックス更新
- **ファイル同期**: ローカルの他フォルダからMarkdownや画像を自動/手動で同期
- **タグ管理**: Frontmatterのタグに基づいたフィルタリング
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

`docker-compose.yml` をテキストエディタで開き、Obsidianの保管庫パスをマウント設定に追加します。

```yaml
# docker-compose.yml の 17行目付近
- {ObsidianのVaultパス}:/0_host_pc:ro
```

**例 (Windowsの場合):**
```yaml
- D:\Documents\Obsidian:/0_host_pc:ro
```
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

http://localhost:8000

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
---
```
