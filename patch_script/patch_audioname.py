import os
import json
import re
from pathvalidate import sanitize_filename

def load_video_data(ndjson_path):
    """
    Load video data from NDJSON file into a dictionary keyed by video_id.
    """
    video_data = {}
    try:
        with open(ndjson_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    video_url = data.get('video_url')
                    if video_url:
                        match = re.search(r'v=([^&]+)', video_url)
                        if match:
                             video_id = match.group(1)
                             video_data[video_id] = data
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        print(f"Error: {ndjson_path} not found.")
    return video_data

def main():
    videos_ndjson = os.getenv('VIDEOS_NDJSON')
    audios_dir = os.getenv('AUDIOS_DIR')

    if not videos_ndjson or not audios_dir:
        print("Error: VIDEOS_NDJSON or AUDIOS_DIR environment variables not set.")
        return

    print(f"Loading video data from {videos_ndjson}...")
    video_map = load_video_data(videos_ndjson)
    print(f"Loaded {len(video_map)} videos.")

    print(f"Scanning directory: {audios_dir}")
    if not os.path.exists(audios_dir):
        print(f"Directory not found: {audios_dir}")
        return

    # Regex to match existing filenames: {publishedAt}_[{video_id}]_{sanitized_title}.mp3
    filename_re = re.compile(r'^(\d{14})_\[([^\]]+)\]_(.*)\.mp3$')

    count_renamed = 0
    count_deleted = 0
    count_skipped = 0

    for filename in os.listdir(audios_dir):
        if not filename.endswith('.mp3'):
            continue

        match = filename_re.match(filename)
        if not match:
            continue

        current_timestamp, video_id, stored_title = match.groups()

        if video_id in video_map:
            video_info = video_map[video_id]
            actual_start_time = video_info.get('actualStartTime')
            title = video_info.get('title')
            
            if not actual_start_time:
                print(f"Skipping {filename}: No actualStartTime found in data.")
                continue

            sanitized_title = sanitize_filename(title)
            new_filename = f"{actual_start_time}_[{video_id}]_{sanitized_title}.mp3"

            if filename != new_filename:
                old_path = os.path.join(audios_dir, filename)
                new_path = os.path.join(audios_dir, new_filename)
                
                # Check if target exists
                if os.path.exists(new_path):
                    # "修正後ファイルと同名のファイルがあった場合は、修正前ファイルを削除する"
                    try:
                        os.remove(old_path)
                        print(f"Deleted duplicate source: {filename} (Target {new_filename} exists)")
                        count_deleted += 1
                    except OSError as e:
                        print(f"Error deleting {filename}: {e}")
                else:
                    try:
                        os.rename(old_path, new_path)
                        print(f"Renamed: {filename} -> {new_filename}")
                        count_renamed += 1
                    except OSError as e:
                        print(f"Error renaming {filename}: {e}")
            else:
                count_skipped += 1
        else:
            print(f"Skipping {filename}: Video ID {video_id} not found in NDJSON.")

    print(f"Finished. Renamed: {count_renamed}, Deleted duplicated source: {count_deleted}, Skipped (already correct): {count_skipped}")

if __name__ == "__main__":
    main()
