
import os
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 設定 ---
ELASTICSEARCH_URL = "http://localhost:9200"
INDEX_NAME = "youtube-chat-logs"
CHAT_LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'chat_logs')
BULK_ENDPOINT = f"{ELASTICSEARCH_URL}/_bulk"
MAX_WORKERS = 4  # 並列処理するスレッド数
# --- 設定ここまで ---

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

def main():
    """
    メイン処理。chat_logsディレクトリ内のJSONファイルを並列で処理する。
    """
    if not os.path.isdir(CHAT_LOGS_DIR):
        print(f"Error: Directory not found at '{CHAT_LOGS_DIR}'")
        return

    json_files = [
        f for f in os.listdir(CHAT_LOGS_DIR)
        if f.endswith('.json') and os.path.getsize(os.path.join(CHAT_LOGS_DIR, f)) > 0
    ]

    if not json_files:
        print("No non-empty JSON files to process.")
        return

    print(f"Found {len(json_files)} files to process. Starting import to index '{INDEX_NAME}'...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 各ファイルに対するペイロード生成と送信タスクを作成
        future_to_file = {
            executor.submit(
                lambda p, f: send_to_elasticsearch(generate_bulk_payload(p, INDEX_NAME), f),
                os.path.join(CHAT_LOGS_DIR, filename),
                filename
            ): filename for filename in json_files
        }

        # 処理が完了したものから結果を表示
        for future in as_completed(future_to_file):
            try:
                result = future.result()
                print(result)
            except Exception as exc:
                print(f"An error occurred processing {future_to_file[future]}: {exc}")

    print("\nImport process finished.")
    # インデックスのドキュメント数を表示して確認
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
