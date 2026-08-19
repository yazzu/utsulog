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

# yt-dlpはYouTube側の仕様変更で頻繁に壊れるため、修正が最速で入るpre-release(nightly)版を使う
RUN pip install --no-cache-dir --pre -U yt-dlp

# アプリケーションコードをコピー
COPY . .
RUN chmod +x run_batch.sh

# 環境変数を設定（オプション）
# ENV PYTHONUNBUFFERED 1

CMD ["tail", "-f", "/dev/null"]
