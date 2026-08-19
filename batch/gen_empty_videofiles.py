import json
import os
import re
from urllib.parse import urlparse, parse_qs
from pathvalidate import sanitize_filename

VIDEOS_NDJSON = os.getenv('VIDEOS_NDJSON')
VIDEOFILES_DIR = os.getenv("VIDEOFILES_DIR")


def main():
    # Ensure output directory exists
    if not os.path.exists(VIDEOFILES_DIR):
        print(f"Creating directory: {VIDEOFILES_DIR}")
        os.makedirs(VIDEOFILES_DIR, exist_ok=True)

    if not os.path.exists(VIDEOS_NDJSON):
        print(f"Error: {VIDEOS_NDJSON} not found.")
        return

    count = 0
    with open(VIDEOS_NDJSON, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                video_info = json.loads(line)
            except json.JSONDecodeError:
                print(f"Failed to parse JSON line: {line[:100]}...")
                continue

            video_url = video_info.get("video_url")
            actual_start_time = video_info.get("actualStartTime")
            video_id = video_info.get("videoId")
            
            # Extract videoId from URL if not explicitly provided
            if not video_id and video_url:
                parsed_url = urlparse(video_url)
                query_params = parse_qs(parsed_url.query)
                video_id = query_params.get('v', [None])[0]
            
            title = video_info.get("title")

            if not actual_start_time or not video_id:
                print(f"Skipping entry due to missing info (actualStartTime={actual_start_time}, videoId={video_id})")
                continue

            # Sanitize filename and build path
            sanitized_title = sanitize_filename(title)
            file_name = f"{actual_start_time}_[{video_id}]_{sanitized_title}.mp4"
            file_path = os.path.join(VIDEOFILES_DIR, file_name)

            # Create empty file if it doesn't exist
            if not os.path.exists(file_path):
                try:
                    with open(file_path, "wb") as empty_file:
                        pass
                    count += 1
                except Exception as e:
                    print(f"Error creating file {file_name}: {e}")
            
    print(f"Finished. Created {count} new empty files in {VIDEOFILES_DIR}.")

if __name__ == "__main__":
    main()
