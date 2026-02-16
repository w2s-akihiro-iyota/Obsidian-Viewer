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
# --workers 1 を指定することで、プロセスの重複を防ぎ、ログの重複も解消します
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]