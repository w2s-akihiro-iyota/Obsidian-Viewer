import asyncio

# 設定変更や同期要求をバックグラウンドタスクに通知するためのイベント
config_updated_event = asyncio.Event()
