
import os
import json
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
import argparse
import tempfile
from urllib.parse import urlparse, parse_qs
from video_membership import get_membership, MembershipUnavailable
from collections import Counter

# --- 設定 ---
# 対象のチャンネルID
CHANNEL_ID = os.getenv('CHANNEL_ID')
# 出力ファイル名
OUTPUT_NDJSON = os.getenv('VIDEOS_NDJSON')

YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'

# JST timezone definition
JST = timezone(timedelta(hours=9))


def get_all_video_ids_from_channel(youtube, channel_id):
    """
    指定されたチャンネルのすべての動画IDを取得する（アップロード再生リスト経由）
    """
    # 1. チャンネル情報からアップロード再生リストIDを取得
    channel_request = youtube.channels().list(
        part='contentDetails',
        id=channel_id
    )
    channel_response = channel_request.execute()

    if 'items' not in channel_response or not channel_response['items']:
        print(f"エラー: チャンネルID '{channel_id}' が見つかりません。")
        return []

    uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

    # 2. アップロード再生リストからすべての動画IDを取得
    video_ids = []
    next_page_token = None
    while True:
        playlist_request = youtube.playlistItems().list(
            part='contentDetails',
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=next_page_token
        )
        playlist_response = playlist_request.execute()

        for item in playlist_response.get('items', []):
            video_ids.append(item['contentDetails']['videoId'])

        next_page_token = playlist_response.get('nextPageToken')
        if not next_page_token:
            break
            
    print(f"Found {len(video_ids)} total videos in the channel.")
    return video_ids

def get_video_details(youtube, video_ids):
    """
    動画IDのリストから、動画の詳細情報を取得する
    """
    video_details = []
    # APIは一度に50件までIDを指定できる
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        videos_request = youtube.videos().list(
            part='snippet,liveStreamingDetails',
            id=','.join(chunk)
        )
        videos_response = videos_request.execute()

        for item in videos_response.get('items', []):
            live_details = item.get('liveStreamingDetails', {})

            title = item['snippet']['title']
            video_id = item['id']
            video_url = f'https://www.youtube.com/watch?v={video_id}'
            # サムネイルURLを取得（高解像度を優先）
            thumbnail_url = item['snippet']['thumbnails'].get('high', {}).get('url')
            
            # 投稿日を取得してフォーマット (JST)
            published_at_iso = item['snippet']['publishedAt']
            published_at_dt = datetime.fromisoformat(published_at_iso.replace('Z', '+00:00'))
            published_at = published_at_dt.astimezone(JST).strftime('%Y%m%d%H%M%S')

            # 配信開始日時を取得してフォーマット (JST)
            actual_start_time_iso = live_details.get('actualStartTime')
            actual_start_time = None
            if actual_start_time_iso:
                actual_start_time_dt = datetime.fromisoformat(actual_start_time_iso.replace('Z', '+00:00'))
                actual_start_time = actual_start_time_dt.astimezone(JST).strftime('%Y%m%d%H%M%S')

            video_details.append({
                'title': title,
                'video_url': video_url,
                'thumbnail_url': thumbnail_url,
                'publishedAt': published_at,
                'actualStartTime': actual_start_time,
                'actualEndTime': format_time(live_details.get('actualEndTime')),
                'isLive': 'liveStreamingDetails' in item
            })
            
    print(f"Got details for {len(video_details)} videos.")
    return video_details

def format_time(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(JST).strftime('%Y%m%d%H%M%S')


def load_previous(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as source:
        return {parse_qs(urlparse(row['video_url']).query)['v'][0]: row
                for line in source if line.strip() for row in [json.loads(line)]}


def collect(youtube, video_ids, previous, membership=get_membership):
    # API errors abort before replacing the previous file. Missing items preserve metadata.
    details = get_video_details(youtube, video_ids)
    fresh = {parse_qs(urlparse(row['video_url']).query)['v'][0]: row for row in details}
    rows = []
    evidence_counts = Counter()
    consecutive_failures = failures = 0
    for video_id in dict.fromkeys(video_ids):
        # Never re-import stale processing statuses or stale confirmed flags from disk.
        row = {key: value for key, value in previous.get(video_id, {}).items()
               if key in ('title', 'video_url', 'thumbnail_url', 'publishedAt')}
        row.update(fresh.get(video_id, {}))
        row.setdefault('video_url', f'https://www.youtube.com/watch?v={video_id}')
        verdict, evidence = membership(video_id)
        evidence_counts[evidence] += 1
        failed = verdict is None and evidence != 'watch_player_offline'
        failures += int(failed)
        consecutive_failures = consecutive_failures + 1 if failed else 0
        checked = len(rows) + 1
        if checked % 25 == 0 or failed:
            print(f'Membership progress: checked={checked} failures={failures} evidence={dict(evidence_counts)}', flush=True)
        if consecutive_failures >= 5 or (checked >= 20 and failures / checked >= 0.25):
            raise MembershipUnavailable('Membership failure threshold exceeded; previous NDJSON was not replaced')
        row['membersOnly'] = verdict
        row['membersOnlyEvidence'] = evidence
        row['membersOnlyCheckedAt'] = datetime.now(timezone.utc).isoformat()
        row['videoDetailsStatus'] = 'ok' if video_id in fresh else 'unavailable'
        rows.append(row)
    print(f'Membership summary: checked={len(rows)} failures={failures} evidence={dict(evidence_counts)}', flush=True)
    return rows


def write_to_ndjson(video_details, file_path):
    directory = os.path.dirname(os.path.abspath(file_path))
    os.makedirs(directory, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                                         delete=False) as output:
            temporary = output.name
            for video in video_details:
                output.write(json.dumps(video, ensure_ascii=False) + '\n')
        mode = os.stat(file_path).st_mode & 0o777 if os.path.exists(file_path) else 0o644
        os.chmod(temporary, mode)
        os.replace(temporary, file_path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--include-index', action='store_true',
                        help='Also recollect every ID stored only in Elasticsearch')
    parser.add_argument('--video-id', action='append', default=[],
                        help='Recollect explicit ID(s); use a separate VIDEOS_NDJSON for a targeted run')
    args = parser.parse_args()
    api_key = os.environ['YOUTUBE_API_KEY']
    youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=api_key)
    previous = load_previous(OUTPUT_NDJSON)
    if args.include_index:
        from import_videos import load_index_videos
        # Only use index metadata as a fallback; processing fields are never re-imported.
        previous = {**load_index_videos(), **previous}
    ids = args.video_id or get_all_video_ids_from_channel(youtube, CHANNEL_ID)
    ids = list(dict.fromkeys([*ids, *previous]))
    if not ids:
        raise RuntimeError('No video IDs found; previous output was not replaced')
    write_to_ndjson(collect(youtube, ids, previous), OUTPUT_NDJSON)


if __name__ == '__main__':
    main()
