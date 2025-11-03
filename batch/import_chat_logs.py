
import os
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import boto3
from botocore.exceptions import ClientError

# --- 設定 ---
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
INDEX_NAME = "youtube-chat-logs"
LOCAL_CHAT_LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'chat_logs')
BULK_ENDPOINT = f"{ELASTICSEARCH_URL}/_bulk"
MAX_WORKERS = 4  # 並列処理するスレッド数
# --- 設定ここまで ---

def create_index_if_not_exists(index_name, es_url):
    """
    指定されたインデックスが存在しない場合、レプリカ数を0に設定して作成する。
    """
    index_url = f"{es_url}/{index_name}"
    try:
        response = requests.head(index_url) # インデックスの存在を確認
        if response.status_code == 404: # インデックスが存在しない場合
            print(f"Index '{index_name}' does not exist. Creating with 0 replicas...")
            settings = {
                "settings": {
                    "number_of_replicas": 0
                }
            }
            create_response = requests.put(index_url, json=settings)
            create_response.raise_for_status()
            print(f"Index '{index_name}' created successfully with 0 replicas.")
        elif response.status_code == 200:
            print(f"Index '{index_name}' already exists.")
        else:
            print(f"Unexpected status code when checking index '{index_name}': {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error checking/creating index '{index_name}': {e}")

def generate_bulk_payload(file_path, index_name):
    """
    単一のNDJSONファイルからBulk API用のペイロード文字列を生成する。
    """
    lines = []
    action_meta = json.dumps({"index": {"_index": index_name}})
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(action_meta)
                    lines.append(line)
        if not lines:
            return None
        return "\n".join(lines) + "\n"
    except Exception as e:
        print(f"Error reading file {os.path.basename(file_path)}: {e}")
        return None

def send_to_elasticsearch(payload, filename):
    """
    生成されたペイロードをElasticsearchに送信する。
    """
    if not payload:
        return f"Skipped (empty or read error): {filename}"

    headers = {"Content-Type": "application/x-ndjson"}
    try:
        response = requests.post(
            BULK_ENDPOINT,
            data=payload.encode('utf-8'),
            headers=headers,
            timeout=60  # タイムアウトを60秒に設定
        )
        response.raise_for_status()
        
        resp_json = response.json()
        if resp_json.get("errors"):
            # 失敗したアイテムの最初のエラー理由を表示
            for item in resp_json.get("items", []):
                if item.get("index", {}).get("error"):
                    error_reason = item["index"]["error"].get("reason", "Unknown error")
                    return f"Failed: {filename} - Reason: {error_reason}"
            return f"Failed: {filename} - Unknown error in response."
        else:
            count = len(resp_json.get("items", []))
            return f"Success: {filename} ({count} docs)"
            
    except requests.exceptions.RequestException as e:
        return f"Failed (RequestException): {filename} - {e}"
    except Exception as e:
        return f"Failed (Exception): {filename} - {e}"

def download_files_from_s3_prefix(bucket_name, s3_prefix, local_dir):
    """
    S3の特定のプレフィックスから全ファイルをダウンロードする
    """
    s3 = boto3.client('s3')
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix=s3_prefix)
    
    download_count = 0
    try:
        os.makedirs(local_dir, exist_ok=True)
        for page in pages:
            for obj in page.get('Contents', []):
                s3_key = obj['Key']
                # プレフィックス自体やフォルダのようなオブジェクトはスキップ
                if s3_key.endswith('/'):
                    continue
                
                local_file_path = os.path.join(local_dir, os.path.basename(s3_key))
                
                print(f"Downloading s3://{bucket_name}/{s3_key} to {local_file_path}")
                s3.download_file(bucket_name, s3_key, local_file_path)
                download_count += 1
        print(f"Downloaded {download_count} files from S3.")
        return True
    except ClientError as e:
        print(f"An error occurred during S3 download: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False

def main():
    """
    メイン処理。chat_logsディレクトリ内のJSONファイルを並列で処理する。
    """
    data_store_type = os.getenv('DATA_STORE_TYPE', 'local')
    target_chat_logs_dir = LOCAL_CHAT_LOGS_DIR

    if data_store_type == 's3':
        bucket_name = os.getenv('S3_BUCKET_NAME')
        if not bucket_name:
            print("Error: S3_BUCKET_NAME environment variable is not set.")
            return
        
        s3_prefix = 'chat_logs/'
        local_tmp_dir = '/tmp/chat_logs'
        
        if not download_files_from_s3_prefix(bucket_name, s3_prefix, local_tmp_dir):
            return
        target_chat_logs_dir = local_tmp_dir

    create_index_if_not_exists(INDEX_NAME, ELASTICSEARCH_URL)

    if not os.path.isdir(target_chat_logs_dir):
        print(f"Error: Directory not found at '{target_chat_logs_dir}'")
        return

    json_files = [
        f for f in os.listdir(target_chat_logs_dir)
        if f.endswith('.json') and os.path.getsize(os.path.join(target_chat_logs_dir, f)) > 0
    ]

    if not json_files:
        print("No non-empty JSON files to process.")
        return

    print(f"Found {len(json_files)} files to process. Starting import to index '{INDEX_NAME}'...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {
            executor.submit(
                lambda p, f: send_to_elasticsearch(generate_bulk_payload(p, INDEX_NAME), f),
                os.path.join(target_chat_logs_dir, filename),
                filename
            ): filename for filename in json_files
        }

        for future in as_completed(future_to_file):
            try:
                result = future.result()
                print(result)
            except Exception as exc:
                print(f"An error occurred processing {future_to_file[future]}: {exc}")

    print("\nImport process finished.")
    try:
        count_url = f"{ELASTICSEARCH_URL}/{INDEX_NAME}/_count"
        response = requests.get(count_url)
        if response.ok:
            total_docs = response.json().get('count', 'N/A')
            print(f"Total documents in index '{INDEX_NAME}': {total_docs}")
    except requests.exceptions.RequestException as e:
        print(f"Could not retrieve document count for index '{INDEX_NAME}'. Is Elasticsearch running?")


if __name__ == "__main__":
    main()
