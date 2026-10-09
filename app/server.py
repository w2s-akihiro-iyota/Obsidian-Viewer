"""
公開用ポートと管理用ポートの 2 つで同じアプリを待ち受ける起動スクリプト

1 プロセス・1 イベントループで 2 つの Uvicorn サーバーを動かすため、
キャッシュ（app.cache）は両ポートで共有される。ワーカー数 1 の制約もそのまま守れる。
管理者かどうかは、リクエストが届いたポートで判定する（app.utils.helpers.is_admin_request）。
"""
import asyncio

import uvicorn

from app.config import PUBLIC_PORT, ADMIN_PORT
from app.main import app


async def serve() -> None:
    """両ポートで待ち受け、どちらかが止まったらもう片方も止める"""
    public_server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PUBLIC_PORT))
    # startup イベント（キャッシュ構築・同期ループ）を 2 回走らせないよう、片方は lifespan を切る
    admin_server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=ADMIN_PORT, lifespan="off"))
    servers = [public_server, admin_server]

    tasks = [asyncio.create_task(s.serve()) for s in servers]
    # 停止シグナルはどちらか一方のサーバーにしか届かないため、残った方へ停止を伝える
    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for s in servers:
        s.should_exit = True
    # 異常終了したサーバーの例外をここで送出し、プロセスを非 0 で終わらせる（restart: always で再起動させる）
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(serve())
