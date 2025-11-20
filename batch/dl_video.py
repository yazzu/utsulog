import os
import json
import yt_dlp
from pathvalidate import sanitize_filename
from urllib.parse import urlparse, parse_qs

# 動画情報が保存されているNDJSONファイルのパス
VIDEOS_NDJSON_PATH = os.getenv('VIDEOS_NDJSON')

def download_video(video_info, save_dir):
    """
    指定された動画情報を元に、yt-dlpを使用して動画をダウンロードする。
    """
    try:
        video_url = video_info.get("video_url")
        published_at = video_info.get("publishedAt")
        video_id = video_info.get("videoId")
        if not video_id and video_url:
            parsed_url = urlparse(video_url)
            query_params = parse_qs(parsed_url.query)
            video_id = query_params.get('v', [None])[0]
        title = video_info.get("title")

        if not all([video_url, published_at, video_id, title]):
            print(f"Skipping due to missing data: {video_info}")
            return

        # ファイル名をサニタイズし、パスを構築
        sanitized_title = sanitize_filename(title)
        file_name = f"{published_at}_[{video_id}]_{sanitized_title}.mp4"
        save_path = os.path.join(save_dir, file_name)

        # ファイルが既に存在する場合はスキップ
        if os.path.exists(save_path):
            print(f"File already exists, skipping: {file_name}")
            return

        print(f"Downloading: {title}")

        # yt-dlpのオプション設定
        ydl_opts = {
            'format': 'bestvideo[height<=360]+bestaudio/best[height<=360]',
            'outtmpl': save_path,
            'merge_output_format': 'mp4',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        print(f"Finished downloading: {file_name}")

    except Exception as e:
        print(f"An error occurred while downloading {video_info.get('title')}: {e}")

def main():
    """
    メイン処理。環境変数から保存先ディレクトリを取得し、動画のダウンロードを実行する。
    """
    # 保存先ディレクトリを環境変数から取得
    save_dir = os.getenv("VIDEOFILES_DIR")
    if not save_dir:
        print("Error: VIDEOFILES_DIR environment variable is not set.")
        return

    # 保存先ディレクトリが存在しない場合は作成
    os.makedirs(save_dir, exist_ok=True)

    # videos.ndjsonから動画情報を読み込んで処理
    try:
        with open(VIDEOS_NDJSON_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    video_info = json.loads(line)
                    download_video(video_info, save_dir)
                except json.JSONDecodeError:
                    print(f"Skipping invalid JSON line: {line.strip()}")
    except FileNotFoundError:
        print(f"Error: {VIDEOS_NDJSON_PATH} not found.")

if __name__ == "__main__":
    main()
