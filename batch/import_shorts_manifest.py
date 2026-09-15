"""Validate a complete yt-dlp Shorts-tab JSON export and persist its IDs."""
import argparse
import json
import os
from pathlib import Path

from shorts import load_manifest, save_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('export', type=Path)
    args = parser.parse_args()
    channel_id = os.environ['CHANNEL_ID']
    data = json.loads(args.export.read_text())
    url = f'https://www.youtube.com/channel/{channel_id}/shorts'
    if data.get('channel_id') != channel_id or data.get('webpage_url') != url:
        raise RuntimeError('Shorts export is for another channel')
    entries = data.get('entries')
    if not isinstance(entries, list) or not entries:
        raise RuntimeError('Shorts export is incomplete')
    ids = set()
    for entry in entries:
        video_id = entry.get('id') if isinstance(entry, dict) else None
        if not video_id or entry.get('url') != f'https://www.youtube.com/shorts/{video_id}':
            raise RuntimeError('Shorts export contains an incomplete entry')
        ids.add(video_id)
    combined = ids | load_manifest(channel_id=channel_id)
    save_manifest(combined, channel_id)
    print(json.dumps({'observed': len(ids), 'known': len(combined)}))


if __name__ == '__main__':
    main()
