
import os
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import boto3
from botocore.exceptions import ClientError

# --- 設定 ---
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL")
ELASTICSEARCH_API_KEY = os.getenv("ELASTICSEARCH_API_KEY")
INDEX_NAME = "youtube-chat-logs"
LOCAL_CHAT_LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'chat_logs')

S3_SOURCE_PREFIX = 'chat_logs/'
S3_PROCESSED_PREFIX = 'chat_logs_processed/'
S3_ERROR_PREFIX = 'chat_logs_error/'

# ELASTICSEARCH_URLが設定されていない場合はエラー
if not ELASTICSEARCH_URL:
    raise ValueError("ELASTICSEARCH_URL environment variable is not set.")

# ELASTICSEARCH_API_KEYが設定されていない場合はエラー
if not ELASTICSEARCH_API_KEY:
    raise ValueError("ELASTICSEARCH_API_KEY environment variable is not set.")

BULK_ENDPOINT = f"{ELASTICSEARCH_URL}/_bulk"
MAX_WORKERS = 4  # 並列処理するスレッド数
# --- 設定ここまで ---

def _get_auth_headers():
    """
    Elasticsearch Serverless用のAPIキー認証ヘッダーを生成する。
    """
    return {
        "Content-Type": "application/x-ndjson",
        "Authorization": f"ApiKey {ELASTICSEARCH_API_KEY}"
    }

def create_index_if_not_exists(index_name, es_url):
    """
    指定されたインデックスが存在しない場合、レプリカ数を0に設定して作成する。
    Elasticsearch Serverlessではレプリカ数の設定は不要だが、互換性のため残す。
    """
    index_url = f"{es_url}/{index_name}"
    headers = _get_auth_headers()
    try:
        response = requests.head(index_url, headers=headers) # インデックスの存在を確認
        if response.status_code == 404: # インデックスが存在しない場合
            print(f"Index '{index_name}' does not exist. Creating...")
            # Serverlessではレプリカ数の設定は無視されるか、エラーになる可能性があるため、設定を削除
            # ただし、既存のコードとの互換性を保つため、空のsettingsでPUTを試みる
            create_response = requests.put(index_url, headers=headers, json={})
            create_response.raise_for_status()
            print(f"Index '{index_name}' created successfully.")
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

def _move_s3_file(s3_client, bucket_name, source_key, destination_prefix):
    """
    S3上のファイルを指定されたプレフィックスに移動するヘルパー関数。
    """
    filename = os.path.basename(source_key)
    destination_key = f"{destination_prefix}{filename}"
    try:
        s3_client.copy_object(
            Bucket=bucket_name,
            CopySource={'Bucket': bucket_name, 'Key': source_key},
            Key=destination_key
        )
        s3_client.delete_object(Bucket=bucket_name, Key=source_key)
        print(f"Moved s3://{bucket_name}/{source_key} to s3://{bucket_name}/{destination_key}")
    except ClientError as e:
        print(f"Error moving S3 file {source_key} to {destination_key}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during S3 file move: {e}")

def send_to_elasticsearch(payload, filename, s3_bucket=None, s3_key=None):
    """
    生成されたペイロードをElasticsearchに送信する。
    S3バケットとキーが指定された場合、成功または失敗に応じてS3上のファイルを移動する。
    """
    if not payload:
        return f"Skipped (empty or read error): {filename}"

    headers = _get_auth_headers()
    s3 = boto3.client('s3') if s3_bucket else None
    
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
                    result_message = f"Failed: {filename} - Reason: {error_reason}"
                    break
            else:
                result_message = f"Failed: {filename} - Unknown error in response."
            
            if s3 and s3_key:
                _move_s3_file(s3, s3_bucket, s3_key, S3_ERROR_PREFIX)
            return result_message
        else:
            count = len(resp_json.get("items", []))
            result_message = f"Success: {filename} ({count} docs)"
            if s3 and s3_key:
                _move_s3_file(s3, s3_bucket, s3_key, S3_PROCESSED_PREFIX)
            return result_message
            
    except requests.exceptions.RequestException as e:
        if s3 and s3_key:
            _move_s3_file(s3, s3_bucket, s3_key, S3_ERROR_PREFIX)
        return f"Failed (RequestException): {filename} - {e}"
    except Exception as e:
        if s3 and s3_key:
            _move_s3_file(s3, s3_bucket, s3_key, S3_ERROR_PREFIX)
        return f"Failed (Exception): {filename} - {e}"

def download_files_from_s3_prefix(bucket_name, s3_prefix, local_dir):
    """
    S3の特定のプレフィックスから全ファイルをダウンロードする
    """
    s3 = boto3.client('s3')
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix=s3_prefix)
    
    download_count = 0
    downloaded_s3_keys = []
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
                downloaded_s3_keys.append(s3_key)
        print(f"Downloaded {download_count} files from S3.")
        return downloaded_s3_keys
    except ClientError as e:
        print(f"An error occurred during S3 download: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []

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
        
        s3_prefix = S3_SOURCE_PREFIX
        local_tmp_dir = '/tmp/chat_logs'
        
        downloaded_s3_keys = download_files_from_s3_prefix(bucket_name, s3_prefix, local_tmp_dir)
        if not downloaded_s3_keys:
            print("No files downloaded from S3 or an error occurred.")
            return
        target_chat_logs_dir = local_tmp_dir

    create_index_if_not_exists(INDEX_NAME, ELASTICSEARCH_URL)

    if not os.path.isdir(target_chat_logs_dir):
        print(f"Error: Directory not found at '{target_chat_logs_dir}'")
        return

    json_files_with_s3_keys = []
    for s3_key in downloaded_s3_keys:
        filename = os.path.basename(s3_key)
        local_file_path = os.path.join(target_chat_logs_dir, filename)
        if os.path.exists(local_file_path) and os.path.getsize(local_file_path) > 0:
            json_files_with_s3_keys.append((local_file_path, filename, s3_key))

    if not json_files_with_s3_keys:
        print("No non-empty JSON files to process.")
        return

    print(f"Found {len(json_files_with_s3_keys)} files to process. Starting import to index '{INDEX_NAME}'...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {
            executor.submit(
                lambda p, f, sk: send_to_elasticsearch(generate_bulk_payload(p, INDEX_NAME), f, bucket_name, sk),
                local_file_path,
                filename,
                s3_key
            ): filename for local_file_path, filename, s3_key in json_files_with_s3_keys
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
        response = requests.get(count_url, headers=_get_auth_headers())
        if response.ok:
            total_docs = response.json().get('count', 'N/A')
            print(f"Total documents in index '{INDEX_NAME}': {total_docs}")
    except requests.exceptions.RequestException as e:
        print(f"Could not retrieve document count for index '{INDEX_NAME}'. Is Elasticsearch running? Error: {e}")


if __name__ == "__main__":
    main()
