import os
import requests
import json
import base64

# --- 設定 ---
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL")
INDEX_NAME = "videos_v2" # ユーザー指定のインデックス名
ELASTICSEARCH_CA = os.getenv('ELASTICSEARCH_CA') # 証明書ファイル名
ELASTICSEARCH_ADMIN = os.getenv('ELASTICSEARCH_ADMIN')
ELASTICSEARCH_PASSWORD = os.getenv('ELASTICSEARCH_PASSWORD')

def _get_auth_headers():
    headers = {
        "Content-Type": "application/json"
    }
    if ELASTICSEARCH_ADMIN and ELASTICSEARCH_PASSWORD:
        auth_str = f"{ELASTICSEARCH_ADMIN}:{ELASTICSEARCH_PASSWORD}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        headers["Authorization"] = f"Basic {encoded_auth}"
    return headers

def patch_videos():
    if not ELASTICSEARCH_URL:
        print("Error: ELASTICSEARCH_URL environment variable is not set.")
        return

    url = f"{ELASTICSEARCH_URL}/{INDEX_NAME}/_update_by_query"
    
    # 全てのドキュメントを対象に更新
    payload = {
        "script": {
            "source": "ctx._source.thumbnail_created = true; ctx._source.thumbnail_uploaded = true;",
            "lang": "painless"
        },
        "query": {
            "match_all": {}
        }
    }

    try:
        print(f"Updating index '{INDEX_NAME}' at {ELASTICSEARCH_URL}...")
        response = requests.post(url, headers=_get_auth_headers(), json=payload, verify=ELASTICSEARCH_CA)
        response.raise_for_status()
        
        result = response.json()
        print("Update successful.")
        print(f"Took: {result.get('took')}ms")
        print(f"Updated: {result.get('updated')} documents")
        print(f"Failures: {result.get('failures')}")

    except requests.exceptions.RequestException as e:
        print(f"Error updating index: {e}")
        if e.response is not None:
            print(f"Response content: {e.response.text}")

if __name__ == "__main__":
    patch_videos()
