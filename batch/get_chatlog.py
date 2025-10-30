
import pytchat
import json
import os

def main():
    # tsvファイルを読み込む
    with open('utsuro_himuro_streams.tsv', 'r', encoding='utf-8') as f:
        next(f)  # Skip header row
        for line in f:
            # タブで分割
            parts = line.strip().split('\t')
            if len(parts) < 2:
                continue

            title, url, *_ = parts

            print(f"Processing: {title}")

            # URLからvideo_idを取得
            try:
                video_id = url.split('v=')[1].split('&')[0]
            except IndexError:
                print(f"  Invalid URL: {url}")
                continue

            # chat_logs ディレクトリがなければ作成
            if not os.path.exists('chat_logs'):
                os.makedirs('chat_logs')

            # JSONファイルの存在チェック
            output_filename = os.path.join('chat_logs', f"{video_id}.json")
            if os.path.exists(output_filename):
                print(f"  Skipping, {output_filename} already exists.")
                continue

            # チャットログを取得
            try:
                chat = pytchat.create(video_id=video_id)
            except pytchat.exceptions.InvalidVideoIdException:
                print(f"  Could not retrieve chat for video ID: {video_id}. The video may be private or deleted.")
                continue
            
            # JSONファイルに書き込み
            with open(output_filename, 'w', encoding='utf-8') as json_file:
                while chat.is_alive():
                    for c in chat.get().items:
                        chat_data = {
                            "videoId": video_id,
                            "datetime": c.datetime,
                            "elapsedTime": c.elapsedTime,
                            "timestamp": c.timestamp,
                            "message": c.message,
                            "authorName": c.author.name,
                            "authorChannelId": c.author.channelId,
                            "id": c.id
                        }
                        json.dump(chat_data, json_file, ensure_ascii=False)
                        json_file.write('\n')

            print(f"  Saved to {output_filename}")

if __name__ == '__main__':
    main()
