"""Retrieve Shorts and persist positive evidence for collectors and importers."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MANIFEST = '/app/videos/shorts-manifest.json'
class ShortsUnavailable(RuntimeError):
    """The Shorts list could not be obtained completely."""


def get_shorts_ids(channel_id, downloader=None):
    if not channel_id:
        raise ShortsUnavailable('CHANNEL_ID is not configured')
    url = f'https://www.youtube.com/channel/{channel_id}/shorts'
    if downloader is None:
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:
            raise ShortsUnavailable('yt-dlp is not installed') from exc
        downloader = YoutubeDL
    options = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': True,
        'ignoreerrors': False,
        'playlistend': None,
        'retries': 2,
        'extractor_retries': 2,
        'sleep_interval_requests': 2,
    }
    try:
        with downloader(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise ShortsUnavailable('Shorts tab retrieval failed') from exc
    if not info or info.get('webpage_url') != url or info.get('channel_id') != channel_id:
        raise ShortsUnavailable('Shorts tab returned no valid playlist')
    entries = info.get('entries')
    if not entries:
        raise ShortsUnavailable('Shorts tab returned no complete entries')
    ids = set()
    for entry in entries:
        if (not entry or not entry.get('id') or
                entry.get('url') != f"https://www.youtube.com/shorts/{entry['id']}"):
            raise ShortsUnavailable('Shorts tab contained an incomplete entry')
        ids.add(entry['id'])
    return ids


def load_manifest(path=None, channel_id=None, required=False):
    path = Path(path or os.getenv('SHORTS_MANIFEST', DEFAULT_MANIFEST))
    if not path.exists():
        if required:
            raise ShortsUnavailable(f'Shorts manifest missing: {path}')
        return set()
    data = json.loads(path.read_text())
    if data.get('channelId') != channel_id or not isinstance(data.get('ids'), list) or not data['ids']:
        raise ShortsUnavailable('Shorts manifest invalid or belongs to another channel')
    return set(data['ids'])


def save_manifest(ids, channel_id, path=None):
    path = Path(path or os.getenv('SHORTS_MANIFEST', DEFAULT_MANIFEST))
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {'channelId': channel_id, 'checkedAt': datetime.now(timezone.utc).isoformat(),
            'evidence': 'youtube_channel_shorts_tab', 'ids': sorted(ids)}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as output:
            temporary = output.name
            json.dump(data, output, ensure_ascii=False)
            output.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
