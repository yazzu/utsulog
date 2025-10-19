
import pytchat
import json
import os

def main():
    # tsvファイルを読み込む
    with open('utsuro_himuro_streams.tsv', 'r', encoding='utf-8') as f:
        for line in f:
            # タブで分割
            parts = line.strip().split('\t')
            if len(parts) < 2:
                continue

            title, url = parts
            print(f"Processing: {title}")

            # URLからvideo_idを取得
            try:
                video_id = url.split('v=')[1]
            except IndexError:
                print(f"  Invalid URL: {url}")
                continue

            # チャットログを取得
            chat = pytchat.create(video_id=video_id)
            
            # chat_logs ディレクトリがなければ作成
            if not os.path.exists('chat_logs'):
                os.makedirs('chat_logs')

            # JSONファイルに書き込み
            output_filename = os.path.join('chat_logs', f"{video_id}.json")
            with open(output_filename, 'w', encoding='utf-8') as json_file:
                while chat.is_alive():
                    for c in chat.get().items:
                        chat_data = {
                            "datetime": c.datetime,
                            "elapsedTime": c.elapsedTime,
                            "timestamp": c.timestamp,
                            "message": c.message,
                            "author_name": c.author.name,
                            "id": c.id
                        }
                        json.dump(chat_data, json_file, ensure_ascii=False)
                        json_file.write('\n')

            print(f"  Saved to {output_filename}")

if __name__ == '__main__':
    main()
