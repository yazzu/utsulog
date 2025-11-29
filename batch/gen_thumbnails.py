import os
import glob
import re
import subprocess
import shutil
import sys
import requests
import json

# --- 設定 ---
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL")
ELASTICSEARCH_API_KEY = os.getenv("ELASTICSEARCH_API_KEY")
INDEX_NAME = os.getenv("VIDEOS_INDEX_NAME")

def _get_auth_headers():
    headers = {"Content-Type": "application/json"}
    if ELASTICSEARCH_API_KEY:
        headers["Authorization"] = f"ApiKey {ELASTICSEARCH_API_KEY}"
    return headers

def get_unprocessed_video_ids():
    """
    Elasticsearchからサムネイル未作成の動画IDリストを取得する
    """
    if not ELASTICSEARCH_URL:
        print("Warning: ELASTICSEARCH_URL not set. Processing all local files.")
        return None

    url = f"{ELASTICSEARCH_URL}/{INDEX_NAME}/_search"
    query = {
        "size": 1000, # 一度に取得する件数。必要に応じてスクロールAPIを使用
        "_source": False, # IDだけ欲しいのでソースは不要
        "query": {
            "bool": {
                "must_not": {
                    "term": {"thumbnail_created": True}
                }
            }
        }
    }

    try:
        response = requests.post(url, headers=_get_auth_headers(), json=query)
        response.raise_for_status()
        hits = response.json().get("hits", {}).get("hits", [])
        # _id が video_id となっている前提
        return set(h["_id"] for h in hits)
    except Exception as e:
        print(f"Error querying Elasticsearch: {e}")
        return None

def update_video_status(video_id):
    """
    Elasticsearch上の動画ステータスを更新する
    """
    if not ELASTICSEARCH_URL:
        return

    url = f"{ELASTICSEARCH_URL}/{INDEX_NAME}/_update/{video_id}"
    payload = {
        "doc": {
            "thumbnail_created": True
        }
    }
    try:
        requests.post(url, headers=_get_auth_headers(), json=payload)
    except Exception as e:
        print(f"  Error updating status for {video_id}: {e}")

def main():
    video_dir = os.environ.get("VIDEOFILES_DIR")
    thumbnails_dir = os.environ.get("THUMBNAILS_DIR")

    if not video_dir or not thumbnails_dir:
        print("Error: VIDEOFILES_DIR or THUMBNAILS_DIR environment variables are not set.")
        sys.exit(1)

    print(f"Video Directory: {video_dir}")
    print(f"Thumbnails Directory: {thumbnails_dir}")

    # Create thumbnails directory if it doesn't exist
    if not os.path.exists(thumbnails_dir):
        os.makedirs(thumbnails_dir)

    # Get list of unprocessed video IDs from Elasticsearch
    unprocessed_ids = get_unprocessed_video_ids()
    if unprocessed_ids is not None:
        print(f"Found {len(unprocessed_ids)} videos pending thumbnail generation in Elasticsearch.")
    print(f"{unprocessed_ids}")
    
    video_files = glob.glob(os.path.join(video_dir, "*.mp4"))
    
    if not video_files:
        print("No .mp4 files found in the video directory.")
        return

    processed_count = 0
    skipped_count = 0

    for video_file in video_files:
        filename = os.path.basename(video_file)
        
        # Extract video_id
        match = re.search(r'_\[(.*?)\]_', filename)
        if not match:
            print(f"Skipping: Could not extract video_id from filename: {filename}")
            continue
        
        video_id = match.group(1)

        # Check if processing is needed
        if unprocessed_ids is not None:
            if video_id not in unprocessed_ids:
                print(f"Skipping {video_id}: Already marked as processed in Elasticsearch.")
                skipped_count += 1
                continue

        print(f"Processing: {filename} (ID: {video_id})")

        # Create a temporary directory for this video's thumbnails
        temp_dir = os.path.join(thumbnails_dir, f"temp_{video_id}")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)

        try:
            # Generate thumbnails using ffmpeg
            output_pattern = os.path.join(temp_dir, "image_%d.jpg")
            command = [
                "ffmpeg",
                "-i", video_file,
                "-vf", "fps=1/180:round=up",
                "-q:v", "2", 
                output_pattern
            ]
            
            # print(f"  Running ffmpeg extraction...")
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Process generated images
            generated_files = sorted(glob.glob(os.path.join(temp_dir, "image_*.jpg")))
            
            if not generated_files:
                 print(f"  Warning: No images generated for {filename}")
            
            for file_path in generated_files:
                filename_only = os.path.basename(file_path)
                index_match = re.search(r'image_(\d+)\.jpg', filename_only)
                if not index_match:
                    continue
                
                index = int(index_match.group(1))
                seconds = (index - 1) * 180
                
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                secs = seconds % 60
                hhmmss = f"{hours:02}{minutes:02}{secs:02}"
                
                new_filename = f"{video_id}_{hhmmss}.webp"
                new_path = os.path.join(thumbnails_dir, new_filename)
                
                convert_command = [
                    "ffmpeg",
                    "-y", # Overwrite output files without asking
                    "-i", file_path,
                    "-q:v", "75", # WebP quality
                    new_path
                ]
                subprocess.run(convert_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            print(f"  Thumbnails generated.")
            
            # Update status in Elasticsearch
            update_video_status(video_id)
            processed_count += 1

        except subprocess.CalledProcessError as e:
            print(f"  Error running ffmpeg: {e}")
        except Exception as e:
            print(f"  An error occurred: {e}")
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    print(f"Process finished. Processed: {processed_count}, Skipped: {skipped_count}")

if __name__ == "__main__":
    main()