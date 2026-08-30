# YouTubeコメント取得〜ES投入バッチ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `youtube-comments_v1`インデックスに向けて、YouTube Data API v3からコメント(トップレベル+返信)を取得しElasticsearchへ投入する新規バッチパイプライン(`get_comments.py` → `import_comments.py`)を構築する。

**Architecture:** 既存の`get_videos.py`/`import_chatlogs.py`と同じ設計思想(`googleapiclient`によるAPI呼び出し、NDJSONへのファイル出力、`_bulk` APIでのES投入、成功/失敗でのファイル移動)を踏襲する2段階パイプライン。取得と変換は1スクリプトに統合し、raw保存ステップは設けない。差分管理は行わず毎回全件再取得+`_id`指定によるupsertで上書きする。

**Tech Stack:** Python 3, `google-api-python-client`(`googleapiclient.discovery.build` / `googleapiclient.errors.HttpError`)、`requests`(Elasticsearch `_bulk` API呼び出し)。いずれも`batch/requirements.txt`に既存。新規依存追加なし。

**Spec:** `docs/superpowers/specs/2026-08-30-youtube-comments-batch-design.md`

## Global Constraints

- 出力ファイル名は`{video_id}_comments.ndjson`とする(チャットログのファイル名と区別するため)。
- 全件再取得+上書き方式とし、差分取得・ローカルの既存ファイルスキップは行わない。
- 返信コメントは`comments.list`で全件取得する(埋め込みの最大5件では打ち切らない)。
- 返信の`id`はYouTube Data APIが返すIDをそのまま使用する(独自の結合加工はしない)。
- `message`フィールドの検索用アナライザーは`kuromoji`のみとし、絵文字の`:alias:`変換は行わない(`textOriginal`をそのまま保存)。
- コメント無効(`commentsDisabled`)の動画はエラーとせず正常系としてスキップする。
- 自動テストは作成せず、実際の動画IDでの手動実行により動作確認する(既存`batch/`の慣習に合わせる)。

---

### Task 1: get_comments.py — 基盤ヘルパー関数

**Files:**
- Create: `batch/get_comments.py`

**Interfaces:**
- Produces: `extract_video_id_from_url(url: str) -> str | None`、`convert_published_at(published_at_iso: str) -> tuple[str, int]`、`is_comments_disabled_error(error: HttpError) -> bool`、`load_videos(videos_ndjson_path: str) -> list[dict]`(各要素は`{'video_id': str, 'title': str}`)、`build_comment_record(snippet: dict, comment_id: str, video_id: str, video_title: str, is_reply: bool, parent_id: str | None) -> dict`(戻り値はスキーマ準拠のdict)

- [ ] **Step 1: `batch/get_comments.py`を作成し、以下の内容を書く**

```python
#!/usr/bin/env python3
"""
YouTube Data API v3 でコメントを取得し、スキーマ形式のNDJSONとして保存するスクリプト
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

JST = timezone(timedelta(hours=9))

YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'


def extract_video_id_from_url(url: str) -> str | None:
    """URLからvideo_idを抽出する"""
    try:
        return url.split('v=')[1].split('&')[0]
    except (IndexError, AttributeError):
        return None


def convert_published_at(published_at_iso: str) -> tuple[str, int]:
    """
    ISO8601(UTC)のpublishedAtを、JSTの表示用文字列とエポックミリ秒に変換する

    Returns:
        tuple: (datetime文字列 "YYYY-MM-DD HH:MM:SS", エポックミリ秒)
    """
    dt = datetime.fromisoformat(published_at_iso.replace('Z', '+00:00'))
    dt_jst = dt.astimezone(JST)
    datetime_str = dt_jst.strftime('%Y-%m-%d %H:%M:%S')
    timestamp_ms = int(dt.timestamp() * 1000)
    return datetime_str, timestamp_ms


def is_comments_disabled_error(error: HttpError) -> bool:
    """
    commentThreads.list が「コメント無効」により失敗したエラーかどうかを判定する
    """
    if error.resp.status != 403:
        return False
    try:
        content = json.loads(error.content.decode('utf-8'))
    except (json.JSONDecodeError, AttributeError):
        return False
    for detail in content.get('error', {}).get('errors', []):
        if detail.get('reason') == 'commentsDisabled':
            return True
    return False


def load_videos(videos_ndjson_path: str) -> list[dict]:
    """
    videos.ndjson を読み込み、[{'video_id': ..., 'title': ...}, ...] を返す
    """
    videos = []
    with open(videos_ndjson_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                video_data = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  [WARN] 行 {line_num}: 不正なJSON形式です - {e}", file=sys.stderr)
                continue
            url = video_data.get('video_url')
            title = video_data.get('title', '')
            video_id = extract_video_id_from_url(url)
            if not video_id:
                print(f"  [WARN] 行 {line_num}: video_idを抽出できません - {url}", file=sys.stderr)
                continue
            videos.append({'video_id': video_id, 'title': title})
    return videos


def build_comment_record(snippet: dict, comment_id: str, video_id: str, video_title: str,
                          is_reply: bool, parent_id: str | None) -> dict:
    """1件のコメントsnippetをスキーマ形式(docs/comment-index-schema.md準拠)のdictに変換する"""
    datetime_str, timestamp_ms = convert_published_at(snippet['publishedAt'])
    return {
        'id': comment_id,
        'videoId': video_id,
        'videoTitle': video_title,
        'type': 'comment',
        'message': snippet.get('textOriginal', ''),
        'authorName': snippet.get('authorDisplayName', ''),
        'authorChannelId': snippet.get('authorChannelId', {}).get('value', ''),
        'publishedAt': snippet['publishedAt'],
        'datetime': datetime_str,
        'timestamp': timestamp_ms,
        'likeCount': snippet.get('likeCount', 0),
        'isReply': is_reply,
        'parentId': parent_id,
    }
```

- [ ] **Step 2: 手動で動作確認する**

以下を実行し、4関数がエラーなく動作し期待通りの値を返すことを確認する:

```bash
cd /home/yazzu709/utsulog
python3 -c "
from batch.get_comments import extract_video_id_from_url, convert_published_at, build_comment_record

assert extract_video_id_from_url('https://www.youtube.com/watch?v=06KIXbb1c0s') == '06KIXbb1c0s'
assert extract_video_id_from_url('invalid') is None

dt_str, ts_ms = convert_published_at('2025-07-06T21:15:32Z')
assert dt_str == '2025-07-07 06:15:32', dt_str
assert ts_ms == 1751829332000, ts_ms

record = build_comment_record(
    {'textOriginal': 'test', 'authorDisplayName': 'name', 'authorChannelId': {'value': 'UCxxx'},
     'publishedAt': '2025-07-06T21:15:32Z', 'likeCount': 3},
    'commentId1', 'videoId1', 'title1', False, None
)
assert record['id'] == 'commentId1'
assert record['isReply'] is False
assert record['parentId'] is None
print('OK')
"
```

Expected: `OK`と出力される(AssertionErrorが出ないこと)。

- [ ] **Step 3: Commit**

```bash
git add batch/get_comments.py
git commit -m "feat: add helper functions for YouTube comments fetch script"
```

---

### Task 2: get_comments.py — コメント取得ロジック(ページング・返信取得)

**Files:**
- Modify: `batch/get_comments.py`(Task 1で作成したファイルに追記)

**Interfaces:**
- Consumes: Task 1の`build_comment_record`, `is_comments_disabled_error`
- Produces: `fetch_additional_replies(youtube, parent_id: str) -> list[dict]`(戻り値は`comments().list`が返す生の`items`)、`fetch_comments_for_video(youtube, video_id: str, video_title: str) -> list[dict]`(戻り値はスキーマ準拠dictのリスト。コメント無効時は空リスト)

- [ ] **Step 1: `batch/get_comments.py`の末尾(`if __name__`より前)に以下を追記する**

```python
def fetch_additional_replies(youtube, parent_id: str) -> list[dict]:
    """
    comments.list を使い、指定した親コメントIDに対する返信を全件取得する
    """
    replies = []
    page_token = None
    while True:
        request = youtube.comments().list(
            part='snippet',
            parentId=parent_id,
            maxResults=100,
            pageToken=page_token
        )
        response = request.execute()
        replies.extend(response.get('items', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    return replies


def fetch_comments_for_video(youtube, video_id: str, video_title: str) -> list[dict]:
    """
    1動画分の全コメント(トップレベル+返信)をスキーマ形式で取得する。
    コメントが無効化されている場合は空リストを返す。
    """
    records = []
    page_token = None
    while True:
        try:
            request = youtube.commentThreads().list(
                part='snippet,replies',
                videoId=video_id,
                maxResults=100,
                pageToken=page_token
            )
            response = request.execute()
        except HttpError as e:
            if is_comments_disabled_error(e):
                print(f"  [INFO] {video_id}: コメントが無効化されています", file=sys.stderr)
                return []
            raise

        for thread in response.get('items', []):
            top_snippet = thread['snippet']['topLevelComment']['snippet']
            top_id = thread['snippet']['topLevelComment']['id']
            records.append(build_comment_record(
                top_snippet, top_id, video_id, video_title,
                is_reply=False, parent_id=None
            ))

            total_reply_count = thread['snippet'].get('totalReplyCount', 0)
            embedded_replies = thread.get('replies', {}).get('comments', [])

            if total_reply_count > len(embedded_replies):
                reply_items = fetch_additional_replies(youtube, top_id)
            else:
                reply_items = embedded_replies

            for reply in reply_items:
                records.append(build_comment_record(
                    reply['snippet'], reply['id'], video_id, video_title,
                    is_reply=True, parent_id=top_id
                ))

        page_token = response.get('nextPageToken')
        if not page_token:
            break

    return records
```

- [ ] **Step 2: 手動で動作確認する**

自チャンネルの実際の動画IDを1つ選び(コメントが存在し、かつコメントが無効化されていないもの)、以下を実行する。`YOUTUBE_API_KEY`は`.env`に設定済みの値を使う。

```bash
cd /home/yazzu709/utsulog
YOUTUBE_API_KEY=$(grep '^YOUTUBE_API_KEY=' .env | cut -d= -f2) python3 -c "
import os
from googleapiclient.discovery import build
from batch.get_comments import fetch_comments_for_video

youtube = build('youtube', 'v3', developerKey=os.environ['YOUTUBE_API_KEY'])
records = fetch_comments_for_video(youtube, '<実際の動画ID>', 'test title')
print(f'{len(records)} 件取得')
for r in records[:3]:
    print(r)
"
```

Expected: エラーなく件数と先頭数件のdictが表示され、`isReply`/`parentId`が想定通りに入っていること。返信が5件を超えるコメントスレッドがある動画であれば、`totalReplyCount`と実際に取得した返信件数が一致することも確認する。

- [ ] **Step 3: Commit**

```bash
git add batch/get_comments.py
git commit -m "feat: add comment thread pagination and reply fetching"
```

---

### Task 3: get_comments.py — 書き出しとmain()の組み立て

**Files:**
- Modify: `batch/get_comments.py`(Task 1・2で作成した関数を利用する`main()`を追加)

**Interfaces:**
- Consumes: Task 1の`load_videos`、Task 2の`fetch_comments_for_video`
- Produces: `write_ndjson(records: list[dict], output_path: str) -> None`、`main()`(スクリプトのエントリポイント)

- [ ] **Step 1: `batch/get_comments.py`の末尾(`fetch_comments_for_video`の後、`if __name__`より前)に以下を追記する**

```python
def write_ndjson(records: list[dict], output_path: str) -> None:
    with open(output_path, 'w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')


def main():
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        print("Error: YOUTUBE_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    videos_ndjson_path = os.getenv('VIDEOS_NDJSON')
    if not videos_ndjson_path or not os.path.exists(videos_ndjson_path):
        print(f"Error: VIDEOS_NDJSON が見つかりません: {videos_ndjson_path}", file=sys.stderr)
        sys.exit(1)

    local_comments_dir = os.getenv('LOCAL_COMMENTS_DIR')
    if not local_comments_dir:
        print("Error: LOCAL_COMMENTS_DIR environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    output_dir = os.path.join(local_comments_dir, 'comments')
    os.makedirs(output_dir, exist_ok=True)

    youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=api_key)

    videos = load_videos(videos_ndjson_path)
    print(f"動画リストを読み込みました: {len(videos)} 件")
    print("-" * 60)

    total_count = 0
    success_count = 0
    empty_count = 0
    error_count = 0

    for video in videos:
        video_id = video['video_id']
        video_title = video['title']
        total_count += 1
        print(f"[{total_count}] {video_title} ({video_id})")

        try:
            records = fetch_comments_for_video(youtube, video_id, video_title)
        except HttpError as e:
            print(f"  [ERROR] {video_id}: APIエラー - {e}", file=sys.stderr)
            error_count += 1
            continue
        except Exception as e:
            print(f"  [ERROR] {video_id}: 予期しないエラー - {type(e).__name__}: {e}", file=sys.stderr)
            error_count += 1
            continue

        if not records:
            empty_count += 1
            continue

        output_file = os.path.join(output_dir, f"{video_id}_comments.ndjson")
        write_ndjson(records, output_file)
        print(f"  [OK] {video_id}: {len(records)} 件のコメントを保存しました -> {output_file}")
        success_count += 1

    print("-" * 60)
    print("処理完了:")
    print(f"  総動画数: {total_count}")
    print(f"  成功: {success_count}")
    print(f"  コメントなし/無効: {empty_count}")
    print(f"  エラー: {error_count}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 手動で動作確認する**

小規模な`videos.ndjson`(2〜3件程度に絞ったコピー)を用意し、実際にスクリプトを実行してファイルが正しく出力されることを確認する。

```bash
cd /home/yazzu709/utsulog
mkdir -p /tmp/comments_test
head -n 3 videos/videos.ndjson > /tmp/videos_test.ndjson
YOUTUBE_API_KEY=$(grep '^YOUTUBE_API_KEY=' .env | cut -d= -f2) \
VIDEOS_NDJSON=/tmp/videos_test.ndjson \
LOCAL_COMMENTS_DIR=/tmp/comments_test \
python3 batch/get_comments.py
ls /tmp/comments_test/comments/
cat /tmp/comments_test/comments/*.ndjson | head -n 3
```

Expected: 処理完了のサマリーが表示され、`{video_id}_comments.ndjson`ファイルが生成され、中身がスキーマ準拠のJSON1行1コメント形式になっていること。コメントが無効な動画が含まれていれば`[INFO] ... コメントが無効化されています`が出力されファイルが作成されないこと。

- [ ] **Step 3: Commit**

```bash
git add batch/get_comments.py
git commit -m "feat: add main entrypoint for get_comments.py"
```

---

### Task 4: import_comments.py の実装

**Files:**
- Create: `batch/import_comments.py`

**Interfaces:**
- Consumes: Task 3が出力する`{LOCAL_COMMENTS_DIR}/comments/{video_id}_comments.ndjson`(各行はTask 1の`build_comment_record`と同じスキーマのJSON、`id`フィールドを含む)
- Produces: なし(スクリプト単体で完結。ES上に`youtube-comments_v1`インデックスとドキュメントを作成する)

- [ ] **Step 1: `batch/import_comments.py`を作成し、以下の内容を書く**

```python
import os
import json
import requests
import base64
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 設定 ---
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL")
INDEX_NAME = os.getenv("COMMENTS_INDEX_NAME", "youtube-comments_v1")
LOCAL_COMMENTS_DIR = os.path.join(os.getenv('LOCAL_COMMENTS_DIR'), "comments")
LOCAL_COMMENTS_PROCESSED_DIR = os.path.join(os.getenv('LOCAL_COMMENTS_DIR'), "comments_processed")
LOCAL_COMMENTS_ERROR_DIR = os.path.join(os.getenv('LOCAL_COMMENTS_DIR'), "comments_error")
ELASTICSEARCH_CA = os.getenv('ELASTICSEARCH_CA')
ELASTICSEARCH_ADMIN = os.getenv('ELASTICSEARCH_ADMIN')
ELASTICSEARCH_PASSWORD = os.getenv('ELASTICSEARCH_PASSWORD')

if not ELASTICSEARCH_URL:
    raise ValueError("ELASTICSEARCH_URL environment variable is not set.")

BULK_ENDPOINT = f"{ELASTICSEARCH_URL}/_bulk"
MAX_WORKERS = 4
# --- 設定ここまで ---


def _get_auth_headers():
    headers = {"Content-Type": "application/x-ndjson"}
    if ELASTICSEARCH_ADMIN and ELASTICSEARCH_PASSWORD:
        auth_str = f"{ELASTICSEARCH_ADMIN}:{ELASTICSEARCH_PASSWORD}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        headers["Authorization"] = f"Basic {encoded_auth}"
    return headers


def create_index_if_not_exists(index_name, es_url):
    """
    指定されたインデックスが存在しない場合、messageフィールドにkuromojiアナライザーを
    設定して作成する。
    """
    index_url = f"{es_url}/{index_name}"
    headers = _get_auth_headers()
    try:
        response = requests.head(index_url, headers=headers, verify=ELASTICSEARCH_CA)
        if response.status_code == 404:
            print(f"Index '{index_name}' does not exist. Creating...")
            settings = {
                "mappings": {
                    "properties": {
                        "message": {
                            "type": "text",
                            "analyzer": "kuromoji"
                        }
                    }
                }
            }
            create_response = requests.put(index_url, headers=headers, json=settings, verify=ELASTICSEARCH_CA)
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
    NDJSONファイルからBulk API用のペイロードを生成する。
    各ドキュメントの `id` フィールドを _id に指定し、同一IDのドキュメントは上書きされる。
    """
    lines = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                doc = json.loads(line)
                doc_id = doc.get('id')
                action_meta = json.dumps({"index": {"_index": index_name, "_id": doc_id}})
                lines.append(action_meta)
                lines.append(line)
        if not lines:
            return None
        return "\n".join(lines) + "\n"
    except Exception as e:
        print(f"Error reading file {os.path.basename(file_path)}: {e}")
        return None


def _move_local_file(source_path, destination_dir):
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
    filename = os.path.basename(file_path)
    if not payload:
        _move_local_file(file_path, LOCAL_COMMENTS_ERROR_DIR)
        return f"Skipped (empty or read error): {filename}"

    headers = _get_auth_headers()
    success = False
    result_message = ""

    try:
        response = requests.post(
            BULK_ENDPOINT,
            data=payload.encode('utf-8'),
            headers=headers,
            timeout=60,
            verify=ELASTICSEARCH_CA
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

    destination_dir = LOCAL_COMMENTS_PROCESSED_DIR if success else LOCAL_COMMENTS_ERROR_DIR
    _move_local_file(file_path, destination_dir)

    return result_message


def main():
    files_to_process = []

    if not LOCAL_COMMENTS_DIR or not os.path.isdir(LOCAL_COMMENTS_DIR):
        print(f"Error: LOCAL_COMMENTS_DIR is not set or not a valid directory.")
        return

    for filename in os.listdir(LOCAL_COMMENTS_DIR):
        if filename.endswith(('.json', '.ndjson')):
            file_path = os.path.join(LOCAL_COMMENTS_DIR, filename)
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
        response = requests.get(count_url, headers=_get_auth_headers(), verify=ELASTICSEARCH_CA)
        if response.ok:
            total_docs = response.json().get('count', 'N/A')
            print(f"Total documents in index '{INDEX_NAME}': {total_docs}")
    except requests.exceptions.RequestException as e:
        print(f"Could not retrieve document count for index '{INDEX_NAME}'. Is Elasticsearch running? Error: {e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 手動で動作確認する**

`docker-compose up elasticsearch`等でローカルのElasticsearchを起動した状態で、Task 3で生成したテスト用NDJSONファイルを使って実行する。

```bash
cd /home/yazzu709/utsulog
mkdir -p /tmp/comments_test/comments
# Task 3で生成した {video_id}_comments.ndjson を /tmp/comments_test/comments/ にコピーしておく
ELASTICSEARCH_URL=https://localhost:9200 \
ELASTICSEARCH_ADMIN=elastic \
ELASTICSEARCH_PASSWORD=<ローカルESのパスワード> \
ELASTICSEARCH_CA=./miniutsuro_es_ca.crt \
COMMENTS_INDEX_NAME=youtube-comments_v1_test \
LOCAL_COMMENTS_DIR=/tmp/comments_test \
python3 batch/import_comments.py

curl -sk -u elastic:<パスワード> https://localhost:9200/youtube-comments_v1_test/_search?pretty | head -n 40
```

Expected: `Index 'youtube-comments_v1_test' does not exist. Creating...`のあと投入が成功し、`_count`が投入件数と一致すること。同じファイルをもう一度投入(`comments_processed/`から`comments/`へ戻して再実行)しても件数が変わらない(重複登録されない)ことを確認し、`_id`によるupsertが機能していることを検証する。確認後、テスト用インデックス`youtube-comments_v1_test`は削除しておく(`curl -sk -u elastic:<パスワード> -XDELETE https://localhost:9200/youtube-comments_v1_test`)。

- [ ] **Step 3: Commit**

```bash
git add batch/import_comments.py
git commit -m "feat: add import_comments.py to bulk-index comments into Elasticsearch"
```

---

### Task 5: run_batch.sh / docker-compose.yml / .env系ファイルの更新

**Files:**
- Modify: `run_batch.sh`
- Modify: `docker-compose.yml`
- Modify: `.env`, `.env.local`, `.env.staging`, `.env.prod`

**Interfaces:**
- Consumes: Task 3の`batch/get_comments.py`、Task 4の`batch/import_comments.py`

- [ ] **Step 1: `run_batch.sh`の`import_chatlogs.py`実行行の直後に以下を追記する**

```bash
echo "Running get_comments.py..."
python batch/get_comments.py
echo "Running import_comments.py..."
python batch/import_comments.py
```

- [ ] **Step 2: `docker-compose.yml`のbatchサービスに、コメント用のvolumeと環境変数を追加する**

`volumes:`の`- ${UTSULOG_DATA}/chat_logs:/app/chat_logs # チャットログ保存用`の行の直後に追加:

```yaml
      - ${UTSULOG_DATA}/comments:/app/comments # コメント保存用
```

`environment:`の`- CHAT_LOGS_INDEX_NAME=${CHAT_LOGS_INDEX_NAME}`の行の直後に追加:

```yaml
      - COMMENTS_INDEX_NAME=${COMMENTS_INDEX_NAME}
```

`environment:`の`- LOCAL_CHAT_LOGS_DIR=/app/chat_logs # チャットログ保存用`の行の直後に追加:

```yaml
      - LOCAL_COMMENTS_DIR=/app/comments # コメント保存用
```

- [ ] **Step 3: `.env`, `.env.local`, `.env.staging`, `.env.prod`それぞれの`CHAT_LOGS_INDEX_NAME=...`行の直後に以下を追記する(値は各ファイルの既存の命名規則に合わせて`youtube-comments_v1`を設定する)**

```
COMMENTS_INDEX_NAME=youtube-comments_v1
```

- [ ] **Step 4: 動作確認する**

```bash
cd /home/yazzu709/utsulog
docker compose config batch
```

Expected: エラーなく設定が展開され、`COMMENTS_INDEX_NAME`と`LOCAL_COMMENTS_DIR=/app/comments`が出力に含まれること。

- [ ] **Step 5: Commit**

```bash
git add run_batch.sh docker-compose.yml .env .env.local .env.staging .env.prod
git commit -m "feat: wire get_comments.py and import_comments.py into the batch pipeline"
```

---

### Task 6: docs/comment-index-schema.md の修正

**Files:**
- Modify: `docs/comment-index-schema.md:39`

**Interfaces:**
- Consumes: なし(ドキュメント修正のみ)

- [ ] **Step 1: `id`フィールドの説明を修正する**

`docs/comment-index-schema.md`の39行目:

修正前:
```
| `id` | keyword | YouTubeコメントID。返信コメントの場合は`{parentCommentId}_{replyId}`のように親IDと組み合わせて一意にする。 |
```

修正後:
```
| `id` | keyword | YouTubeコメントID。返信コメントも含め、YouTube Data APIが返すグローバルに一意なコメントIDをそのまま使用する。 |
```

- [ ] **Step 2: 変更内容を確認する**

```bash
git diff docs/comment-index-schema.md
```

Expected: 39行目のみが変更されていること。

- [ ] **Step 3: Commit**

```bash
git add docs/comment-index-schema.md
git commit -m "docs: clarify that reply comment ids reuse the YouTube API id verbatim"
```
