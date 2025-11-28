#!/bin/bash

# スクリプトが失敗したら即座に終了する
set -e

echo "Starting batch process..."

# 1. 動画リストの取得とS3へのアップロード
echo "Running get_videos.py..."
python batch/get_videos.py
echo "Running get_chatlogs.py..."
python batch/get_chatlogs.py
echo "Running import_videos.py..."
python batch/import_videos.py
echo "Running import_chatlogs.py..."
python batch/import_chatlogs.py
echo "Running dl_video.py..."
python batch/dl_video.py
echo "Running gen_thumbnails.py..."
python batch/gen_thumbnails.py
echo "Running upload_thumbnails.py..."
python batch/upload_thumbnails.py
echo "Batch process finished successfully."
