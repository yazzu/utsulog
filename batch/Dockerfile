# Python 3.11をベースイメージとして使用
FROM python:3.11-slim

# 作業ディレクトリを設定
WORKDIR /app

# ffmpegをインストール
RUN apt-get update && \
    apt-get install -y ffmpeg nodejs npm && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 依存関係ファイルをコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .
RUN chmod +x run_batch.sh

# 環境変数を設定（オプション）
# ENV PYTHONUNBUFFERED 1

CMD ["tail", "-f", "/dev/null"]
