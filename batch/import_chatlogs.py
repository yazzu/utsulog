
import os
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil

# --- 設定 ---
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL")
ELASTICSEARCH_API_KEY = os.getenv("ELASTICSEARCH_API_KEY")
INDEX_NAME = os.getenv("CHAT_LOGS_INDEX_NAME", "youtube-chat-logs")
LOCAL_CHAT_LOGS_DIR = os.path.join(os.getenv('LOCAL_CHAT_LOGS_DIR'), "chat_logs")
LOCAL_CHAT_LOGS_PROCESSED_DIR = os.path.join(os.getenv('LOCAL_CHAT_LOGS_DIR'), "chat_logs_processed")
LOCAL_CHAT_LOGS_ERROR_DIR = os.path.join(os.getenv('LOCAL_CHAT_LOGS_DIR'), "chat_logs_error")

# ELASTICSEARCH_URLが設定されていない場合はエラー
if not ELASTICSEARCH_URL:
    raise ValueError("ELASTICSEARCH_URL environment variable is not set.")

# ELASTICSEARCH_API_KEYが設定されていない場合は、認証なしで接続を試みる

BULK_ENDPOINT = f"{ELASTICSEARCH_URL}/_bulk"
MAX_WORKERS = 4  # 並列処理するスレッド数
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

def _move_local_file(source_path, destination_dir):
    """
    ローカルファイルを指定されたディレクトリに移動するヘルパー関数。
    """
    if not destination_dir:
        print(f"Warning: Destination directory not set. Cannot move {os.path.basename(source_path)}")
        return
    try:
        os.makedirs(destination_dir, exist_ok=True)
        destination_path = os.path.join(destination_dir, os.path.basename(source_path))
        shutil.move(source_path, destination_path)
        print(f"Moved {os.path.basename(source_path)} to {destination_dir}")
    except Exception as e:
        print(f"Error moving file {source_path} to {destination_dir}: {e}")

def send_to_elasticsearch(payload, file_path):
    """
    生成されたペイロードをElasticsearchに送信する。
    データストアのタイプに応じて、成功または失敗したファイルを移動する。
    """
    filename = os.path.basename(file_path)
    if not payload:
        _move_local_file(file_path, LOCAL_CHAT_LOGS_ERROR_DIR)
        return f"Skipped (empty or read error): {filename}"

    headers = _get_auth_headers()
    success = False
    result_message = ""

    try:
        response = requests.post(
            BULK_ENDPOINT,
            data=payload.encode('utf-8'),
            headers=headers,
            timeout=60
        )
        response.raise_for_status()
        
        resp_json = response.json()
        if resp_json.get("errors"):
            for item in resp_json.get("items", []):
                if item.get("index", {}).get("error"):
                    error_reason = item["index"]["error"].get("reason", "Unknown error")
                    result_message = f"Failed: {filename} - Reason: {error_reason}"
                    break
            else:
                result_message = f"Failed: {filename} - Unknown error in response."
            success = False
        else:
            count = len(resp_json.get("items", []))
            result_message = f"Success: {filename} ({count} docs)"
            success = True
            
    except requests.exceptions.RequestException as e:
        result_message = f"Failed (RequestException): {filename} - {e}"
        success = False
    except Exception as e:
        result_message = f"Failed (Exception): {filename} - {e}"
        success = False

    # 処理結果に基づいてファイルを移動
    destination_dir = LOCAL_CHAT_LOGS_PROCESSED_DIR if success else LOCAL_CHAT_LOGS_ERROR_DIR
    _move_local_file(file_path, destination_dir)
        
    return result_message

def main():
    """
    メイン処理。ローカルディレクトリからJSONファイルを並列で処理する。
    """
    files_to_process = []

    if not LOCAL_CHAT_LOGS_DIR or not os.path.isdir(LOCAL_CHAT_LOGS_DIR):
        print(f"Error: LOCAL_CHAT_LOGS_DIR is not set or not a valid directory.")
        return

    for filename in os.listdir(LOCAL_CHAT_LOGS_DIR):
        if filename.endswith(('.json', '.ndjson')):
            file_path = os.path.join(LOCAL_CHAT_LOGS_DIR, filename)
            if os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                files_to_process.append({'path': file_path})

    create_index_if_not_exists(INDEX_NAME, ELASTICSEARCH_URL)

    if not files_to_process:
        print("No non-empty JSON files to process.")
        return

    print(f"Found {len(files_to_process)} files to process. Starting import to index '{INDEX_NAME}'...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {
            executor.submit(
                send_to_elasticsearch,
                generate_bulk_payload(file_info['path'], INDEX_NAME),
                file_info['path']
            ): os.path.basename(file_info['path']) for file_info in files_to_process
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
