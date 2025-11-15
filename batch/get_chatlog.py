
import pytchat
import json
import os
import boto3
from botocore.exceptions import NoCredentialsError, ClientError

def upload_to_s3(local_file_path, bucket_name, s3_file_name):
    """
    ファイルをS3にアップロードする
    """
    s3 = boto3.client('s3')
    try:
        s3.upload_file(local_file_path, bucket_name, s3_file_name)
        print(f"  Successfully uploaded {os.path.basename(local_file_path)} to s3://{bucket_name}/{s3_file_name}")
        return True
    except FileNotFoundError:
        print(f"  Error: The file was not found: {local_file_path}")
        return False
    except NoCredentialsError:
        print("  Error: AWS credentials not found.")
        return False
    except Exception as e:
        print(f"  An unexpected error occurred during S3 upload: {e}")
        return False

def download_from_s3(bucket_name, s3_file_name, local_file_path):
    """
    S3からファイルをダウンロードする
    """
    s3 = boto3.client('s3')
    try:
        print(f"Downloading s3://{bucket_name}/{s3_file_name} to {local_file_path}")
        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
        s3.download_file(bucket_name, s3_file_name, local_file_path)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"Error: The object does not exist in S3: s3://{bucket_name}/{s3_file_name}")
        else:
            print(f"An unexpected error occurred during S3 download: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False

def s3_object_exists(bucket_name, s3_object_name):
    """
    S3にオブジェクトが存在するかどうかを確認する
    """
    s3 = boto3.client('s3')
    try:
        s3.head_object(Bucket=bucket_name, Key=s3_object_name)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            # その他のClientError（例：権限不足）は再送出
            print(f"  Error checking S3 object existence: {e}")
            raise

def main():
    # 環境変数を取得
    data_store_type = os.getenv('DATA_STORE_TYPE', 'local')
    bucket_name = os.getenv('S3_BUCKET_NAME')
    proxy_url = os.getenv('PROXY_URL') # プロキシURLを環境変数から取得

    if data_store_type == 's3' and not bucket_name:
        print("Error: DATA_STORE_TYPE is 's3' but S3_BUCKET_NAME environment variable is not set.")
        return

    # 処理対象の動画リストファイルパスを決定
    video_list_file = 'videos/videos.ndjson'
    if data_store_type == 's3':
        s3_object_name = 'videos/videos.ndjson'
        local_tmp_path = '/tmp/videos.ndjson'
        if not download_from_s3(bucket_name, s3_object_name, local_tmp_path):
            return
        video_list_file = local_tmp_path

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
            local_chat_logs_dir = 'chat_logs'
            if not os.path.exists(local_chat_logs_dir):
                os.makedirs(local_chat_logs_dir)

            # JSONファイルの存在チェック
            output_filename = os.path.join(local_chat_logs_dir, f"{video_id}.json")
            if os.path.exists(output_filename):
                print(f"  Skipping, {output_filename} already exists.")
                continue

            # S3モードの場合、まずS3にファイルが存在するかチェック
            if data_store_type == 's3':
                s3_object_name = os.path.join('chat_logs', f"{video_id}.json")
                try:
                    if s3_object_exists(bucket_name, s3_object_name):
                        print(f"  Skipping, s3://{bucket_name}/{s3_object_name} already exists.")
                        continue
                except ClientError:
                    print(f"  Could not check for object existence in S3. Halting.")
                    break

            # チャットログを取得
            try:
                if proxy_url:
                    chat = pytchat.create(video_id=video_id, proxy=proxy_url)
                else:
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
                            "message": c.message,
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

            # S3モードの場合はアップロード
            if data_store_type == 's3':
                s3_object_name = os.path.join('chat_logs', f"{video_id}.json")
                upload_to_s3(output_filename, bucket_name, s3_object_name)


if __name__ == '__main__':
    main()
