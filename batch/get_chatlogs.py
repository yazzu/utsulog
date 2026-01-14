
import pytchat
import json
import os
import emoji

def main():
    # 処理対象の動画リストファイルパスを決定
    video_list_file = os.getenv('VIDEOS_NDJSON')
    local_chat_logs_dir = os.path.join(os.getenv('LOCAL_CHAT_LOGS_DIR'), "chat_logs")
    local_chat_logs_processed_dir = os.path.join(os.getenv('LOCAL_CHAT_LOGS_DIR'), "chat_logs_processed")

    if not os.path.exists(video_list_file):
        print(f"Error: Video list file not found at '{video_list_file}'")
        return

    # videos.ndjson ファイルを読み込む
    with open(video_list_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                video_data = json.loads(line)
                title = video_data.get('title')
                url = video_data.get('video_url')

                if not title or not url:
                    print(f"  Skipping line due to missing 'title' or 'video_url': {line.strip()}")
                    continue
            except json.JSONDecodeError:
                print(f"  Skipping invalid JSON line: {line.strip()}")
                continue

            print(f"Processing: {title}")

            # URLからvideo_idを取得
            try:
                video_id = url.split('v=')[1].split('&')[0]
            except IndexError:
                print(f"  Invalid URL: {url}")
                continue

            # chat_logs ディレクトリがなければ作成
            if not os.path.exists(local_chat_logs_dir):
                os.makedirs(local_chat_logs_dir)
            output_filename = os.path.join(local_chat_logs_dir, f"{video_id}.json")

            # JSONファイルの存在チェック
            check_filename = os.path.join(local_chat_logs_processed_dir, f"{video_id}.json")
            if os.path.exists(check_filename):
                print(f"  Skipping, {check_filename} already exists.")
                continue

            # チャットログを取得
            try:
                chat = pytchat.create(video_id=video_id)
            except pytchat.exceptions.InvalidVideoIdException as e:
                print(f"  Could not retrieve chat for video ID: {video_id}. The video may be private or deleted. Error: {e}")
                continue
            
            # JSONファイルに書き込み
            with open(output_filename, 'w', encoding='utf-8') as json_file:
                has_content = False
                while chat.is_alive():
                    for c in chat.get().items:
                        has_content = True
                        chat_data = {
                            "videoId": video_id,
                            "videoTitle": title,
                            "datetime": c.datetime,
                            "elapsedTime": c.elapsedTime,
                            "timestamp": c.timestamp,
                            "type": "chat",
                            "message": emoji.emojize(c.message, language='alias'),
                            "authorName": c.author.name,
                            "authorChannelId": c.author.channelId,
                            "id": c.id
                        }
                        json.dump(chat_data, json_file, ensure_ascii=False)
                        json_file.write('\n')
            
            if not has_content:
                print(f"  No chat logs found for {video_id}. The local file is empty.")
                # 空のファイルは削除
                os.remove(output_filename)
                continue

            print(f"  Saved to {output_filename}")

if __name__ == '__main__':
    main()
