import os
import json
import requests
from elasticsearch import Elasticsearch
from googleapiclient.discovery import build
import boto3
from botocore.exceptions import ClientError
from PIL import Image
from io import BytesIO
import time

# --- Configuration ---
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL")
ELASTICSEARCH_API_KEY = os.getenv("ELASTICSEARCH_API_KEY")
CHAT_LOGS_INDEX_NAME = os.getenv("CHAT_LOGS_INDEX_NAME", "youtube-chat-logs_v2")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
S3_BUCKET_NAME = os.getenv("S3_AUTHOR_ICON_BUCKET_NAME", "utsulog-author-icons")
AUTHOR_ICONS_DIR = os.getenv("AUTHOR_ICONS_DIR", "/mnt/f/Dev/utsulog/author-icons")

# --- Setup ---
if not os.path.exists(AUTHOR_ICONS_DIR):
    os.makedirs(AUTHOR_ICONS_DIR, exist_ok=True)

def get_unique_author_channel_ids(es):
    """
    Get all unique authorChannelIds from Elasticsearch using aggregation.
    """
    print("Fetching unique authorChannelIds from Elasticsearch...")
    query = {
        "size": 0,
        "aggs": {
            "unique_authors": {
                "terms": {
                    "field": "authorChannelId.keyword",
                    "size": 30000  # Adjust size as needed
                }
            }
        }
    }
    
    try:
        response = es.search(index=CHAT_LOGS_INDEX_NAME, body=query)
        buckets = response["aggregations"]["unique_authors"]["buckets"]
        author_ids = [b["key"] for b in buckets]
        print(f"Found {len(author_ids)} unique authorChannelIds.")
        return author_ids
    except Exception as e:
        print(f"Error fetching from Elasticsearch: {e}")
        return []

def get_channel_thumbnails(youtube, channel_ids):
    """
    Get thumbnail URLs for a list of channel IDs using YouTube API.
    """
    thumbnails = {}
    # YouTube API allows up to 50 IDs per request
    chunk_size = 50
    
    for i in range(0, len(channel_ids), chunk_size):
        chunk = channel_ids[i:i+chunk_size]
        try:
            request = youtube.channels().list(
                part="snippet",
                id=",".join(chunk)
            )
            response = request.execute()
            
            for item in response.get("items", []):
                channel_id = item["id"]
                # Try to get high resolution, fallback to default
                url = item["snippet"]["thumbnails"].get("high", {}).get("url")
                if not url:
                    url = item["snippet"]["thumbnails"].get("default", {}).get("url")
                
                if url:
                    thumbnails[channel_id] = url
            
            print(f"Fetched details for {len(chunk)} channels...")
            
        except Exception as e:
            print(f"Error fetching channel details: {e}")
            
    return thumbnails

def download_and_convert_image(url, channel_id):
    """
    Download image from URL, convert to WebP, and save to disk.
    Returns the path to the saved file.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        img = Image.open(BytesIO(response.content))
        
        # Convert to RGB if necessary (e.g. for PNG with transparency)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        output_path = os.path.join(AUTHOR_ICONS_DIR, f"{channel_id}.webp")
        img.save(output_path, "WEBP")
        return output_path
    except Exception as e:
        print(f"Error processing image for {channel_id}: {e}")
        return None

def upload_to_s3(file_path, bucket, object_name):
    """
    Upload a file to an S3 bucket.
    """
    s3_client = boto3.client('s3')
    try:
        s3_client.upload_file(file_path, bucket, object_name, ExtraArgs={'ContentType': 'image/webp'})
        # print(f"Uploaded {object_name} to S3.")
        return True
    except ClientError as e:
        print(f"Error uploading to S3: {e}")
        return False

def main():
    # 1. Connect to Elasticsearch
    if ELASTICSEARCH_API_KEY:
        es = Elasticsearch(ELASTICSEARCH_URL, api_key=ELASTICSEARCH_API_KEY)
    else:
        es = Elasticsearch(ELASTICSEARCH_URL)

    # 2. Connect to YouTube API
    if not YOUTUBE_API_KEY:
        print("Error: YOUTUBE_API_KEY not set.")
        return
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

    # 3. Get Author IDs
    author_ids = get_unique_author_channel_ids(es)
    if not author_ids:
        return

    # 4. Check which icons are already processed (optional optimization)
    # For now, we can check if the file exists locally to avoid re-downloading
    # But to be safe and update potentially changed icons, we might want to re-fetch.
    # Let's check local files to skip.
    
    ids_to_fetch = []
    for aid in author_ids:
        if not os.path.exists(os.path.join(AUTHOR_ICONS_DIR, f"{aid}.webp")):
            ids_to_fetch.append(aid)
    
    print(f"{len(ids_to_fetch)} icons need to be fetched.")
    
    if not ids_to_fetch:
        print("All icons are already present locally. Checking S3 upload...")
        # If we want to ensure S3 upload, we can iterate all author_ids
        ids_to_process = author_ids
    else:
        ids_to_process = ids_to_fetch

    # 5. Fetch URLs from YouTube
    # Only fetch for those we are going to process
    # Note: If we are just re-uploading, we don't need to fetch URLs, but the logic below combines them.
    # Let's simplify: Fetch URLs for ids_to_fetch.
    
    url_map = {}
    if ids_to_fetch:
        url_map = get_channel_thumbnails(youtube, ids_to_fetch)

    # 6. Download, Convert, and Upload
    # We iterate over ALL author_ids to ensure everything is on S3
    # But we only download if we have a URL (which implies it was in ids_to_fetch) OR if it exists locally.
    
    processed_count = 0
    uploaded_count = 0
    
    for aid in author_ids:
        local_path = os.path.join(AUTHOR_ICONS_DIR, f"{aid}.webp")
        
        # If not exists locally, try to download
        if not os.path.exists(local_path):
            if aid in url_map:
                print(f"Downloading icon for {aid}...")
                saved_path = download_and_convert_image(url_map[aid], aid)
                if saved_path:
                    processed_count += 1
                else:
                    continue # Failed to download
            else:
                # No URL found or failed to fetch URL
                continue
        
        # Now local file should exist
        if os.path.exists(local_path):
            # Upload to S3
            # We can check if object exists in S3 to avoid redundant writes, but standard put is fine for now.
            # To save time/cost, maybe we should skip if we didn't just download it?
            # The requirement implies we should ensure they are on S3.
            # Let's upload.
            object_name = f"{aid}.webp"
            if upload_to_s3(local_path, S3_BUCKET_NAME, object_name):
                uploaded_count += 1
                if uploaded_count % 10 == 0:
                    print(f"Uploaded {uploaded_count} icons...")

    print(f"Done. Processed {processed_count} new images. Uploaded {uploaded_count} images to S3.")

if __name__ == "__main__":
    main()
