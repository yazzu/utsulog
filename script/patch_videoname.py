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
                    # Use existing fields. Note: get_videos.py saves keys as:
                    # 'title', 'video_url', 'thumbnail_url', 'publishedAt', 'actualStartTime'
                    # checking video_url for ID if not explicitly stored (though get_videos does not seem to save video_id explicitly in the dict based on my read, wait, let me re-check get_videos.py content)
                    
                    # Re-reading get_videos.py content from memory:
                    # video_details.append({ ... 'video_url': video_url ... })
                    # It does NOT save 'video_id' explicitly as a top level key in the dict output in write_to_ndjson.
                    # But video_url has it.
                    
                    video_url = data.get('video_url')
                    if video_url:
                        # Simple extraction assuming standard format
                        # https://www.youtube.com/watch?v=VIDEO_ID
                        # or similar.
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
    videofiles_dir = os.getenv('VIDEOFILES_DIR')

    if not videos_ndjson or not videofiles_dir:
        print("Error: VIDEOS_NDJSON or VIDEOFILES_DIR environment variables not set.")
        return

    print(f"Loading video data from {videos_ndjson}...")
    video_map = load_video_data(videos_ndjson)
    print(f"Loaded {len(video_map)} videos.")

    print(f"Scanning directory: {videofiles_dir}")
    if not os.path.exists(videofiles_dir):
        print(f"Directory not found: {videofiles_dir}")
        return

    # Regex to match existing filenames: {publishedAt}_[{video_id}]_{sanitized_title}.mp4
    # timestamp is usually 14 digits (YYYYMMDDHHMMSS)
    # But let's be flexible on the first part, and anchor on `_[{video_id}]_`
    filename_re = re.compile(r'^(\d{14})_\[([^\]]+)\]_(.*)\.mp4$')

    count_renamed = 0
    count_skipped = 0

    for filename in os.listdir(videofiles_dir):
        if not filename.endswith('.mp4'):
            continue

        match = filename_re.match(filename)
        if not match:
            # Try to support already renamed files or other formats just in case?
            # For now, strictly follow the "Before" pattern implies we only touch those matching.
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
            new_filename = f"{actual_start_time}_[{video_id}]_{sanitized_title}.mp4"

            if filename != new_filename:
                old_path = os.path.join(videofiles_dir, filename)
                new_path = os.path.join(videofiles_dir, new_filename)
                
                # Check if target exists
                if os.path.exists(new_path):
                    print(f"Skipping rename {filename} -> {new_filename}: Target already exists.")
                    continue
                
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

    print(f"Finished. Renamed: {count_renamed}, Skipped (already correct): {count_skipped}")

if __name__ == "__main__":
    main()
