import os
import requests
import json
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
import boto3
from botocore.exceptions import ClientError

# --- 設定 ---
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL")
ELASTICSEARCH_API_KEY = os.getenv("ELASTICSEARCH_API_KEY")
INDEX_NAME = os.getenv("VIDEOS_INDEX_NAME")
# ローカルで実行する際のデフォルトファイルパス
LOCAL_NDJSON_FILE = os.getenv('VIDEOS_NDJSON')

# ELASTICSEARCH_URLが設定されていない場合はエラー
if not ELASTICSEARCH_URL:
    raise ValueError("ELASTICSEARCH_URL environment variable is not set.")

# ELASTICSEARCH_API_KEYが設定されていない場合は、認証なしで接続を試みる

BULK_ENDPOINT = f"{ELASTICSEARCH_URL}/_bulk"
MAX_WORKERS = 4  # 並列処理するスレッド数
CHUNK_SIZE = 500 # 1回のリクエストで送信するドキュメント数
# --- 設定ここまで ---

def _get_auth_headers():
    """
    Elasticsearch Serverless用のAPIキー認証ヘッダーを生成する。
    APIキーが設定されていない場合は認証ヘッダーを含めない。
    """
    headers = {
        "Content-Type": "application/x-ndjson"
    }
    if ELASTICSEARCH_API_KEY:
        headers["Authorization"] = f"ApiKey {ELASTICSEARCH_API_KEY}"
    return headers

def create_index_if_not_exists(index_name, es_url):
    """
    指定されたインデックスが存在しない場合、作成する。
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

def extract_video_id(video_info):
    """
    動画情報からvideo_idを抽出する
    """
    video_id = video_info.get("videoId")
    video_url = video_info.get("video_url")
    if not video_id and video_url:
        try:
            parsed_url = urlparse(video_url)
            query_params = parse_qs(parsed_url.query)
            video_id = query_params.get('v', [None])[0]
        except Exception:
            pass
    return video_id

def generate_bulk_payload_from_chunk(chunk, index_name):
    """
    NDJSONのチャンク（行のリスト）からBulk API用のペイロード文字列を生成する。
    doc_as_upsertを使用して、既存のフィールド（処理ステータス等）を維持する。
    """
    lines = []
    for line in chunk:
        line = line.strip()
        if not line:
            continue
        
        try:
            video_info = json.loads(line)
            video_id = extract_video_id(video_info)
            
            if not video_id:
                # video_idがない場合は自動ID生成になるが、ステータス管理のためにはIDが必要
                # ここではスキップするか、元の行をそのまま送るか。
                # 一貫性のため、video_id必須とするのが望ましいが、フォールバックとしてindexアクションを使う
                action_meta = json.dumps({"index": {"_index": index_name}})
                lines.append(action_meta)
                lines.append(line)
            else:
                # updateアクションとdoc_as_upsertを使用
                action_meta = json.dumps({"update": {"_index": index_name, "_id": video_id}})
                doc_payload = json.dumps({"doc": video_info, "doc_as_upsert": True})
                lines.append(action_meta)
                lines.append(doc_payload)
                
        except json.JSONDecodeError:
            continue

    if not lines:
        return None
    return "\n".join(lines) + "\n"

def send_to_elasticsearch(payload, chunk_index):
    """
    生成されたペイロードをElasticsearchに送信する。
    """
    if not payload:
        return f"Skipped chunk {chunk_index} (empty)."

    headers = _get_auth_headers()
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
            # エラー内容をもう少し詳細に出力
            error_details = []
            for item in resp_json.get("items", []):
                action_key = next(iter(item)) # "index" or "update"
                if item[action_key].get("error"):
                    error_reason = item[action_key]["error"].get("reason", "Unknown error")
                    error_details.append(f"ID {item[action_key].get('_id', 'unknown')}: {error_reason}")
            
            # エラーが多すぎる場合は最初の5件だけ表示
            error_msg = "; ".join(error_details[:5])
            if len(error_details) > 5:
                error_msg += f" ... and {len(error_details) - 5} more errors."
            return f"Failed chunk {chunk_index}: {error_msg}"
        else:
            count = len(resp_json.get("items", []))
            return f"Success: chunk {chunk_index} ({count} docs)"
            
    except requests.exceptions.RequestException as e:
        return f"Failed chunk {chunk_index} (RequestException): {e}"
    except Exception as e:
        return f"Failed chunk {chunk_index} (Exception): {e}"

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

def main():
    """
    メイン処理。NDJSONファイルをチャンクに分割し、並列で処理する。
    """
    data_store_type = os.getenv('DATA_STORE_TYPE', 'local')
    target_ndjson_file = LOCAL_NDJSON_FILE

    if data_store_type == 's3':
        bucket_name = os.getenv('S3_BUCKET_NAME')
        if not bucket_name:
            print("Error: S3_BUCKET_NAME environment variable is not set.")
            return
        
        s3_object_name = os.path.join('videos', os.path.basename(LOCAL_NDJSON_FILE))
        local_tmp_path = os.path.join('/tmp', os.path.basename(LOCAL_NDJSON_FILE))
        
        if not download_from_s3(bucket_name, s3_object_name, local_tmp_path):
            return
        target_ndjson_file = local_tmp_path
    
    # インデックス削除処理（delete_index_if_exists）は廃止
    create_index_if_not_exists(INDEX_NAME, ELASTICSEARCH_URL)

    if not os.path.isfile(target_ndjson_file):
        print(f"Error: File not found at '{target_ndjson_file}'")
        return

    print(f"Starting import of '{os.path.basename(target_ndjson_file)}' to index '{INDEX_NAME}' (Upsert Mode)...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        chunk_index = 0
        with open(target_ndjson_file, 'r', encoding='utf-8') as f:
            while True:
                chunk = [line for _, line in zip(range(CHUNK_SIZE), f)]
                if not chunk:
                    break
                
                chunk_index += 1
                payload = generate_bulk_payload_from_chunk(chunk, INDEX_NAME)
                if payload:
                    futures.append(executor.submit(send_to_elasticsearch, payload, chunk_index))
        
        for future in as_completed(futures):
            try:
                result = future.result()
                print(result)
            except Exception as exc:
                print(f"An error occurred during processing a chunk: {exc}")

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