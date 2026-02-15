# 1. Python環境の準備
FROM python:3.11-slim

# 2. フォルダの作成と移動
WORKDIR /app

# 3. 必要なライブラリのインストール
# キャッシュを利用してビルドを速くするため、まずrequirementsだけコピーします
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. プログラム一式をコピー
COPY . .

# 5. アプリの起動設定
# --host 0.0.0.0 を指定しないと、Docker外部（ブラウザ）からアクセスできません
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]