
import os
import csv
from datetime import datetime
from googleapiclient.discovery import build

# --- 設定 ---
# APIキーを読み込むファイル
API_KEY_FILE = 'api_key.txt'
# 対象のチャンネルID
CHANNEL_ID = 'UC64MV1Dfq3prs9CccXg09rQ'  # 氷室うつろさん
# 出力ファイル名
OUTPUT_TSV = 'utsuro_himuro_streams.tsv'

YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'

def load_api_key(file_path):
    """
    ファイルからAPIキーを読み込む
    ファイル形式: APIKEY = '...'
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            line = f.readline()
            if "APIKEY = '" in line:
                return line.split("'")[1]
    except FileNotFoundError:
        print(f"エラー: APIキーファイルが見つかりません: {file_path}")
    except IndexError:
        print(f"エラー: APIキーファイル '{file_path}' の形式が正しくありません。")
    return None


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
            # ライブ配信の詳細情報がないものは除外
            if 'liveStreamingDetails' not in item:
                continue

            title = item['snippet']['title']
            video_id = item['id']
            video_url = f'https://www.youtube.com/watch?v={video_id}'
            # サムネイルURLを取得（高解像度を優先）
            thumnail_url = item['snippet']['thumbnails'].get('high', {}).get('url')
            
            # 投稿日を取得してフォーマット
            published_at_iso = item['snippet']['publishedAt']
            published_at_dt = datetime.fromisoformat(published_at_iso.replace('Z', '+00:00'))
            published_at = published_at_dt.strftime('%Y%m%d%H%M%S')


            video_details.append({
                'title': title,
                'video_url': video_url,
                'thumnail_url': thumnail_url,
                'publishedAt': published_at
            })
            
    print(f"Got details for {len(video_details)} videos.")
    return video_details

def write_to_tsv(video_details, file_path):
    """
    動画詳細情報のリストをTSVファイルに書き込む
    """
    if not video_details:
        print("No video details to write.")
        return

    with open(file_path, 'w', newline='', encoding='utf-8') as tsvfile:
        # overview_batch.md のカラム順に合わせる
        fieldnames = ['title', 'video_url', 'thumnail_url', 'publishedAt']
        writer = csv.DictWriter(tsvfile, fieldnames=fieldnames, delimiter='	')

        writer.writeheader()
        
        for video in video_details:
            writer.writerow(video)
            
    print(f"Successfully wrote data to {file_path}")


def main():
    """
    メイン処理
    """
    API_KEY = load_api_key(API_KEY_FILE)
    if not API_KEY:
        return

    youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=API_KEY)

    # 1. チャンネルの全動画IDを取得
    video_ids = get_all_video_ids_from_channel(youtube, CHANNEL_ID)

    if not video_ids:
        print("No stream videos found for this channel.")
        return

    # 2. 各動画の詳細情報を取得
    video_details = get_video_details(youtube, video_ids)

    # 3. TSVファイルに書き込み
    write_to_tsv(video_details, OUTPUT_TSV)

if __name__ == '__main__':
    main()
