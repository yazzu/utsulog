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
