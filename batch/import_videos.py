import os
import requests
import json
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64

# --- 設定 ---
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL")
INDEX_NAME = os.getenv("VIDEOS_INDEX_NAME")
# ローカルで実行する際のデフォルトファイルパス
LOCAL_NDJSON_FILE = os.getenv('VIDEOS_NDJSON')
ELASTICSEARCH_CA = os.getenv('ELASTICSEARCH_CA') # 証明書ファイル名
ELASTICSEARCH_ADMIN = os.getenv('ELASTICSEARCH_ADMIN')
ELASTICSEARCH_PASSWORD = os.getenv('ELASTICSEARCH_PASSWORD')

# ELASTICSEARCH_URLが設定されていない場合はエラー
if not ELASTICSEARCH_URL:
    raise ValueError("ELASTICSEARCH_URL environment variable is not set.")

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
    if ELASTICSEARCH_ADMIN and ELASTICSEARCH_PASSWORD:
        auth_str = f"{ELASTICSEARCH_ADMIN}:{ELASTICSEARCH_PASSWORD}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        headers["Authorization"] = f"Basic {encoded_auth}"
    return headers

def create_index_if_not_exists(index_name, es_url):
    """
    指定されたインデックスが存在しない場合、作成する。
    """
    index_url = f"{es_url}/{index_name}"
    headers = _get_auth_headers()
    headers['Content-Type'] = 'application/json'
    properties = {
        'isLive': {'type': 'boolean'},
        'membersOnly': {'type': 'boolean'},
        'actualEndTime': {'type': 'keyword'},
        'membersOnlyEvidence': {'type': 'keyword'},
        'membersOnlyCheckedAt': {'type': 'date'},
        'videoDetailsStatus': {'type': 'keyword'},
    }
    response = requests.head(index_url, headers=headers, verify=ELASTICSEARCH_CA, timeout=30)
    if response.status_code == 404:
        response = requests.put(index_url, headers=headers,
                                json={'mappings': {'properties': properties}},
                                verify=ELASTICSEARCH_CA, timeout=30)
        response.raise_for_status()
    else:
        response.raise_for_status()
        response = requests.put(f'{index_url}/_mapping', headers=headers,
                                json={'properties': properties},
                                verify=ELASTICSEARCH_CA, timeout=30)
        response.raise_for_status()


def load_index_videos():
    """Read all IDs with a scroll; never delete/recreate the existing index."""
    headers = _get_auth_headers()
    headers['Content-Type'] = 'application/json'
    kwargs = dict(headers=headers, verify=ELASTICSEARCH_CA, timeout=60)
    response = requests.post(f'{ELASTICSEARCH_URL}/{INDEX_NAME}/_search',
                             params={'scroll': '2m'},
                             json={'size': 500, 'sort': ['_doc'], 'query': {'match_all': {}},
                                   '_source': ['title', 'video_url', 'thumbnail_url', 'publishedAt']},
                             **kwargs)
    response.raise_for_status()
    page = response.json()
    scroll_id = page.get('_scroll_id')
    videos = {}
    try:
        while page['hits']['hits']:
            for hit in page['hits']['hits']:
                row = hit.get('_source', {})
                row.setdefault('video_url', f"https://www.youtube.com/watch?v={hit['_id']}")
                videos[hit['_id']] = row
            if not scroll_id:
                raise RuntimeError('Missing scroll ID; refusing an incomplete backfill')
            response = requests.post(f'{ELASTICSEARCH_URL}/_search/scroll',
                                     json={'scroll': '2m', 'scroll_id': scroll_id}, **kwargs)
            response.raise_for_status()
            page = response.json()
            scroll_id = page.get('_scroll_id', scroll_id)
    finally:
        if scroll_id:
            response = requests.delete(f'{ELASTICSEARCH_URL}/_search/scroll',
                                       json={'scroll_id': [scroll_id]}, **kwargs)
            response.raise_for_status()
    return videos


def extract_video_id(video_info):
    """
    動画情報からvideo_idを抽出する
    """
    video_url = video_info.get("video_url")
    if video_url:
        try:
            parsed_url = urlparse(video_url)
            query_params = parse_qs(parsed_url.query)
            video_id = query_params.get('v', [None])[0]
            return video_id
        except Exception as e:
            pass

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
            if video_info.get('videoDetailsStatus') == 'unavailable':
                for field in ('title', 'thumbnail_url', 'publishedAt', 'actualStartTime', 'actualEndTime', 'isLive'):
                    video_info.pop(field, None)
            for field in ('membersOnly', 'isLive'):
                if video_info.get(field) is None:
                    video_info.pop(field, None)
                elif type(video_info[field]) is not bool:
                    raise ValueError(f'{field} must be boolean or null')
            video_id = extract_video_id(video_info)
            if video_id:
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
            timeout=60,  # タイムアウトを60秒に設定
            verify=ELASTICSEARCH_CA
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

def main():
    """
    メイン処理。NDJSONファイルをチャンクに分割し、並列で処理する。
    """
    target_ndjson_file = LOCAL_NDJSON_FILE
    
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
        
        failures = []
        for future in as_completed(futures):
            try:
                result = future.result()
                print(result)
                if result.startswith('Failed'):
                    failures.append(result)
            except Exception as exc:
                failures.append(str(exc))

    if failures:
        raise RuntimeError("Import failed: " + "; ".join(failures))
    print("\nImport process finished.")
    try:
        count_url = f"{ELASTICSEARCH_URL}/{INDEX_NAME}/_count"
        response = requests.get(count_url, headers=_get_auth_headers(), verify=ELASTICSEARCH_CA)
        if response.ok:
            total_docs = response.json().get('count', 'N/A')
            print(f"Total documents in index '{INDEX_NAME}': {total_docs}")
    except requests.exceptions.RequestException as e:
        print(f"Could not retrieve document count for index '{INDEX_NAME}'. Is Elasticsearch running? Error: {e}")


if __name__ == "__main__":
    main()