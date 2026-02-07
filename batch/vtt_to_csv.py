import os
import json
import re
import hashlib
from datetime import datetime
from glob import glob

# Environment variables
VIDEOS_NDJSON_PATH = os.getenv('VIDEOS_NDJSON')
SUBTITLES_DIR = os.getenv('SUBTITLES_DIR')
LOCAL_CHAT_LOGS_DIR = os.getenv('LOCAL_CHAT_LOGS_DIR')

def load_video_metadata(ndjson_path):
    """
    Load video metadata from the ndjson file into a dictionary keyed by videoId.
    """
    video_metadata = {}
    if not ndjson_path or not os.path.exists(ndjson_path):
        print(f"Warning: VIDEOS_NDJSON not found at {ndjson_path}")
        return video_metadata

    try:
        with open(ndjson_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    video_id = data.get('video_url', '').split('v=')[-1].split('&')[0]
                    if video_id:
                        video_metadata[video_id] = data
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error reading {ndjson_path}: {e}")
    
    return video_metadata

def parse_vtt_time(time_str):
    """
    Parse VTT timestamp (HH:MM:SS.mmm or MM:SS.mmm) to milliseconds.
    """
    parts = time_str.split(':')
    seconds = 0
    if len(parts) == 3:
        seconds += int(parts[0]) * 3600
        seconds += int(parts[1]) * 60
        seconds += float(parts[2])
    elif len(parts) == 2:
        seconds += int(parts[0]) * 60
        seconds += float(parts[1])
    else:
        return 0
    return int(seconds * 1000)

def parse_vtt_file(vtt_path):
    """
    Parse a VTT file and yield cues (start_time_ms, message).
    This is a simple parser assuming standard WebVTT format.
    """
    cues = []
    try:
        with open(vtt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Simple state machine
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if '-->' in line:
                # Found a timing line
                time_parts = line.split(' --> ')
                if len(time_parts) >= 2:
                    start_time = parse_vtt_time(time_parts[0])
                    # end_time = parse_vtt_time(time_parts[1].split(' ')[0]) 
                    
                    # Read text lines until empty line or next cue
                    message_lines = []
                    i += 1
                    while i < len(lines):
                        text_line = lines[i].strip()
                        if not text_line:
                            break
                        # Check if next line looks like a timestamp (handling tight packing)
                        if '-->' in text_line:
                            i -= 1 # Backtrack
                            break
                        if parse_vtt_time_check(text_line): # Extra safety check for timestamp line
                             i -= 1
                             break
                             
                        message_lines.append(text_line)
                        i += 1
                    
                    message = ' '.join(message_lines).strip()
                    if message:
                        cues.append((start_time, message))
            else:
                i += 1
                
    except Exception as e:
        print(f"Error parsing {vtt_path}: {e}")
    
    return cues

def parse_vtt_time_check(line):
    # Simple check if line looks like "00:00:00.000 --> 00:00:05.000"
    return '-->' in line

def format_elapsed_time(ms):
    """
    Format milliseconds to H:MM:SS or M:SS without leading zeros on hours/minutes.
    Example: 17000 -> 0:17
    """
    seconds = int(ms / 1000)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02}:{s:02}"
    else:
        return f"{m}:{s:02}"

def generate_id(video_id, timestamp_ms, message):
    """
    Generate a unique ID for the chat message.
    """
    raw_str = f"{video_id}-{timestamp_ms}-{message}"
    return hashlib.sha1(raw_str.encode('utf-8')).hexdigest()

def main():
    if not SUBTITLES_DIR or not os.path.isdir(SUBTITLES_DIR):
        print("Error: SUBTITLES_DIR environment variable is not set or valid.")
        return
    
    if not LOCAL_CHAT_LOGS_DIR:
        print("Error: LOCAL_CHAT_LOGS_DIR environment variable is not set.")
        return
    
    output_dir = os.path.join(LOCAL_CHAT_LOGS_DIR, "chat_logs")
    os.makedirs(output_dir, exist_ok=True)

    video_metadata = load_video_metadata(VIDEOS_NDJSON_PATH)
    
    # Pattern: {datetime}_{videoId}_{title}_fixed.vtt
    # We will iterate all files, but filter by suffix
    vtt_files = glob(os.path.join(SUBTITLES_DIR, "*_fixed.vtt"))
    
    print(f"Found {len(vtt_files)} VTT files to process.")

    for vtt_path in vtt_files:
        basename = os.path.basename(vtt_path)
        # Regex to extract videoId. 
        # Filename format: YYYYMMDDHHMMSS_[VIDEOID]_TITLE_fixed.vtt
        # Be careful as TITLE might contain underscores or brackets.
        # We rely on the structure: DATE_[ID]_...
        
        match = re.match(r'(\d{14})_\[([^\]]+)\]_(.+)_fixed\.vtt', basename)
        if not match:
            print(f"Skipping file with unexpected format: {basename}")
            continue
            
        file_datetime_str = match.group(1)
        video_id = match.group(2)
        # title_from_filename = match.group(3)

        output_filename = basename.replace('_fixed.vtt', '_vtt.json')
        output_path = os.path.join(output_dir, output_filename)
        
        if os.path.exists(output_path):
            print(f"Skipping {basename}, output already exists.")
            continue
            
        print(f"Processing {basename}...")
        
        # Get metadata
        meta = video_metadata.get(video_id)
        video_title = meta.get('title', '') if meta else ''
        actual_start_time_str = meta.get('actualStartTime', '') if meta else ''
        
        # Convert published_at to unixtime ms
        # Format: 20251130061527 -> YYYYMMDDHHMMSS
        # If actualStartTime is available from valid source (ndjson), use it. 
        # Otherwise fallback to filename date? Filename date is usually download time or publish time.
        # Step description says: datetime: videos.ndjson.actualStartTime + vtt.datetime
        
        base_timestamp = 0
        if actual_start_time_str:
             try:
                 dt = datetime.strptime(actual_start_time_str, "%Y%m%d%H%M%S")
                 base_timestamp = int(dt.timestamp() * 1000)
             except ValueError:
                 pass
        
        if base_timestamp == 0:
             # Fallback to filename datetime
             try:
                 dt = datetime.strptime(file_datetime_str, "%Y%m%d%H%M%S")
                 base_timestamp = int(dt.timestamp() * 1000)
             except ValueError:
                 pass

        cues = parse_vtt_file(vtt_path)
        
        with open(output_path, 'w', encoding='utf-8') as out_f:
            for start_ms, message in cues:
                
                # timestamp = actualStartTime + elapsed (start_ms)
                abs_timestamp = base_timestamp + start_ms
                
                record = {
                    "videoId": video_id,
                    "videoTitle": video_title,
                    "datetime": datetime.fromtimestamp(abs_timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S'), # This is readable string
                    "elapsedTime": format_elapsed_time(start_ms),
                    "timestamp": abs_timestamp,
                    "type": "transcript",
                    "message": message,
                    "authorName": "@Utsuro_himuro",
                    "authorChannelId": "UC64MV1Dfq3prs9CccXg09rQ",
                    "id": generate_id(video_id, start_ms, message)
                }
                
                # Write NDJSON line
                json.dump(record, out_f, ensure_ascii=False)
                out_f.write('\n')
        
        print(f"Generated {output_path}")

if __name__ == "__main__":
    main()
