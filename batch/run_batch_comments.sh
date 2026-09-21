#!/bin/bash

# スクリプトが失敗したら即座に終了する
set -e

echo "Starting comments batch process..."

echo "Running get_comments.py..."
python batch/get_comments.py
echo "Running import_comments.py..."
python batch/import_comments.py

echo "Comments batch process finished successfully."
