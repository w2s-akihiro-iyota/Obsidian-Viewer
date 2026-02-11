---
tags:
  - docker
  - 開発Tips
  - 技術
aliases: 
created: 木曜日, 4月 17日 2025, 6:21:00 午後
modified: 水曜日, 4月 23日 2025, 6:00:08 午後
---

# 🐳 Docker & Redis コマンド一覧表

## ✅ Docker コマンド

| 目的                    | コマンド                                               | 補足・説明                |
| --------------------- | -------------------------------------------------- | -------------------- |
| Redis コンテナ起動          | `docker run -d --name my-redis -p 6379:6379 redis` | 初回のみ。「-d」はバックグラウンド実行 |
| 実行中のコンテナ一覧            | `docker ps`                                        | 今まさに動いてるコンテナだけを表示    |
| 全コンテナ一覧（停止含む）         | `docker ps -a`                                     | 停止済みのコンテナも含めて表示      |
| コンテナの停止               | `docker stop my-redis`                             | 起動中のコンテナを停止          |
| コンテナの再起動（停止→再開）       | `docker start my-redis`                            | 既存コンテナを再起動           |
| コンテナの強制再起動            | `docker restart my-redis`                          | 停止＋起動を一発で            |
| Redis ログ確認            | `docker logs my-redis`                             | エラーログなど確認に便利         |
| コンテナ削除                | `docker rm my-redis`                               | 停止中のコンテナのみ削除可能       |
| Docker バージョン確認        | `docker --version`                                 | インストール確認などに使う        |
| Docker 全体の状態確認        | `docker info`                                      | 設定・環境・ステータス確認        |
| WSL 状態確認              | `wsl --status`                                     | WSL のバージョンなど確認可能     |
| WSL の更新               | `wsl --update`                                     | Docker 動作に必要なことあり    |
| redis-cli コンテナの中に入る   | `docker exec -it my-redis redis-cli`               | Redis CLI に入って操作可能   |
| redis 内で一番容量の大きいキーを取得 | `docker exec -it my-redis redis-cli --memkeys`     |                      |

| 目的                    | コマンド                                           | 補足・説明                      |
| --------------------- | ---------------------------------------------- | -------------------------- |
| redis-cli コンテナの中に入る   | `docker exec -it my-redis redis-cli`           | Redis CLI に入って操作可能できるようになる |
| redis 内で一番容量の大きいキーを取得 | `docker exec -it my-redis redis-cli --memkeys` |                            |

---

## 🧠 Redis CLI コマンド（redis-cli 内）

| 目的            | コマンド              | 補足・説明                                       |
| ------------- | ----------------- | ------------------------------------------- |
| キーの作成（セット）    | `set mykey hello` | `mykey` に `hello` を保存                       |
| キーの取得         | `get mykey`       | `mykey` の中身を見る                              |
| キーの削除         | `del mykey`       | `mykey` を削除                                 |
| キーの一覧取得       | `keys *`          | すべてのキーを取得（開発用）<br>※ 本番環境では利用しないほうがいい（負荷が高い） |
| 特定パターンのキー一覧   | `keys user:*`     | 例：user: で始まるキーを取得                           |
| 有効期限の確認       | `ttl mykey`       | `ttl` + `キー名` で指定した有効期限を確認                  |
| Redis CLI を終了 | `exit`            | redis-cli から抜ける                             |
|               |                   |                                             |

---

## 📌 注意点

- `keys *` は本番では非推奨（負荷が高いため）
- 開発・検証目的なら問題なく使って OK！
- コンテナの再起動は `docker start`、新規作成は `docker run` と覚えよう！

---
