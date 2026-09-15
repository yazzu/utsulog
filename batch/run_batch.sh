#!/bin/bash

# スクリプトが失敗したら即座に終了する
set -e

echo "Starting batch process..."

# 1. 動画リストの取得とS3へのアップロード
echo "Running get_videos.py..."
python batch/get_videos.py
echo "Validating Shorts manifest..."
python - <<'PY'
import os
import sys
sys.path.insert(0, 'batch')
from shorts import load_manifest

ids = load_manifest(channel_id=os.environ['CHANNEL_ID'], required=True)
print(f"Shorts manifest validated: {len(ids)} IDs")
PY
echo "Running get_chatlogs.py..."
python batch/get_chatlogs.py
#echo "Running convert_chat_to_ndjson.py..."
#python batch/convert_chat_to_ndjson.py
echo "Running import_videos.py..."
python batch/import_videos.py
echo "Running import_chatlogs.py..."
python batch/import_chatlogs.py
echo "Running get_comments.py..."
python batch/get_comments.py
echo "Running import_comments.py..."
python batch/import_comments.py
echo "Running dl_video.py..."
python batch/dl_video.py
echo "Running gen_thumbnails.py..."
python batch/gen_thumbnails.py
echo "Waiting 5 seconds for index refresh..."
sleep 5
echo "Running upload_thumbnails.py..."
python batch/upload_thumbnails.py
echo "Running backup_to_s3.py..."
python batch/backup_to_s3.py
echo "Batch process finished successfully."
