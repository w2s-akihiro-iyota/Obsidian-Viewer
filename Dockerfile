# 1. Python環境の準備
FROM python:3.11-slim

# 2. フォルダの作成と移動
WORKDIR /app

# 3. 必要なライブラリのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. プログラム一式をコピー
COPY . .

# 5. アプリの起動設定
# 1 プロセスで公開用（8000）と管理用（8001）の 2 ポートを待ち受けます（app/server.py）
# プロセスを 1 つに保つことで、キャッシュの共有とログの重複防止を両立します
CMD ["python", "-m", "app.server"]