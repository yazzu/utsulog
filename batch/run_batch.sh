#!/bin/bash

# スクリプトが失敗したら即座に終了する
set -e

echo "Starting batch process..."

# 1. 動画リストの取得とS3へのアップロード
echo "Running get_videos.py..."
python /app/get_videos.py
echo
echo "Batch process finished successfully."
