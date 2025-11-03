# Python 3.9をベースイメージとして使用
FROM python:3.9-slim

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係ファイルをコピーしてインストール
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . /app

# 環境変数を設定（オプション）
# ENV PYTHONUNBUFFERED 1

CMD ["tail", "-f", "/dev/null"]
