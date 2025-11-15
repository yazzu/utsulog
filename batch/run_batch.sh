#!/bin/bash

# スクリプトが失敗したら即座に終了する
set -e

echo "Starting batch process..."

# 1. 動画リストの取得とS3へのアップロード
echo "Running import_videos.py..."
python /app/import_videos.py
echo "Running import_chat_logs.py..."
python /app/import_chat_logs.py
echo
echo "Batch process finished successfully."
