---
tags:
  - Redis
  - docker
  - 開発Tips
aliases:
created: 火曜日, 4月 22日 2025, 11:43:37 午前
modified: 月曜日, 1月 19日 2026, 5:42:36 午後
publish: "TRUE"
---

## Redis 環境構築手順書（Docker 利用）

このドキュメントでは、Docker を使ってローカルに Redis サーバーを構築し、接続や動作確認を行う手順を説明します。

---

### 📦 前提条件

- Docker Desktop がインストールされていること
  👉 ダウンロード: https://www.docker.com/products/docker-desktop/

- PowerShell / Terminal / WSL などの CLI が使用できること

---

### 🐳 手順 0. Docker Desctop を起動する

- インストールした Docker Ｄesctop のアプリケーションを実行し Docker を起動する

### 🚀 手順 1. Redis コンテナを起動する

以下のコマンドを実行し、Redis サーバーを Docker で起動します。

```bash
docker run --name my-redis -p 6379:6379 -d redis
```

| オプション             | 説明                        |
| ----------------- | ------------------------- |
| `--name my-redis` | コンテナ名                     |
| `-p 6379:6379`    | ホスト: コンテナのポートマッピング        |
| `-d`              | バックグラウンドで起動（detached モード） |
| `redis`           | 使用する公式イメージ                |

### 🔎 手順 2. Redis に接続して動作確認

#### ① Redis CLI に接続する

これで Redis に保存した値の確認などができる

```bash
docker exec -it my-redis redis-cli
```

#### ② 簡単な操作

| 目的            | コマンド              | 補足・説明                                       |
| ------------- | ----------------- | ------------------------------------------- |
| キーの作成（セット）    | `set mykey hello` | `mykey` に `hello` を保存                       |
| キーの取得         | `get mykey`       | `mykey` の中身を見る                              |
| キーの削除         | `del mykey`       | `mykey` を削除                                 |
| キーの一覧取得       | `keys *`          | すべてのキーを取得（開発用）<br>※ 本番環境では利用しないほうがいい（負荷が高い） |
| 特定パターンのキー一覧   | `keys user:*`     | 例：user: で始まるキーを取得                           |
| 有効期限の確認       | `ttl mykey`       | `ttl` + `キー名` で指定した有効期限を確認                  |
| Redis CLI を終了 | `exit`            | redis-cli から抜ける                             |

### 🧪 手順 4. 設定値を変更し開発環境から接続する

- 開発用.config にて下記の設定にする

| 設定値                                | 値                |
| ---------------------------------- | ---------------- |
| `Setting_Redis_Connection_Enabled` | `TRUE`           |
| `Setting_Redis_Connection_String`  | `localhost:6379` |

## 🛑 その他. Redis コンテナの停止・削除（必要に応じて）

| 説明  | コマンド                    |
| --- | ----------------------- |
| 停止  | `docker stop my-redis`  |
| 再起動 | `docker start my-redis` |
| 削除  | `docker rm -f my-redis` |
