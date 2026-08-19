#!/usr/bin/env python3
"""
Raw chat logs を NDJSON 形式に変換するスクリプト

raw_chat_logs ディレクトリから chat-downloader で取得した生データを読み込み、
整形した NDJSON 形式で chat_logs ディレクトリに保存します。
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
import emoji


# 日本時間タイムゾーン
JST = timezone(timedelta(hours=9))


def extract_video_id_from_url(url: str) -> str:
    """URLからvideo_idを抽出する"""
    try:
        return url.split('v=')[1].split('&')[0]
    except (IndexError, AttributeError):
        return None


def load_video_metadata(videos_ndjson_path: str) -> dict:
    """
    videos.ndjson から videoId -> title のマッピングを作成する
    
    Returns:
        dict: {video_id: title} のマッピング
    """
    video_metadata = {}
    
    if not os.path.exists(videos_ndjson_path):
        print(f"Warning: videos.ndjson が見つかりません: {videos_ndjson_path}", file=sys.stderr)
        return video_metadata
    
    with open(videos_ndjson_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            
            try:
                video_data = json.loads(line)
                url = video_data.get('video_url')
                title = video_data.get('title', '')
                
                if url:
                    video_id = extract_video_id_from_url(url)
                    if video_id:
                        video_metadata[video_id] = title
            except json.JSONDecodeError as e:
                print(f"  [WARN] 行 {line_num}: 不正なJSON形式です - {e}", file=sys.stderr)
                continue
    
    print(f"動画メタデータを読み込みました: {len(video_metadata)} 件")
    return video_metadata


def convert_timestamp_to_datetime(timestamp_us: int) -> str:
    """
    マイクロ秒タイムスタンプを JST の datetime 文字列に変換する
    
    Args:
        timestamp_us: マイクロ秒単位のタイムスタンプ
    
    Returns:
        str: YYYY-MM-DD HH:MM:SS 形式の文字列
    """
    try:
        # マイクロ秒を秒に変換
        timestamp_sec = timestamp_us / 1_000_000
        dt = datetime.fromtimestamp(timestamp_sec, tz=JST)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, OSError, OverflowError):
        return ""


def convert_raw_chat_to_ndjson(raw_message: dict, video_id: str, video_title: str) -> dict | None:
    """
    raw_chat_logs の1行を NDJSON 形式に変換する
    
    Args:
        raw_message: chat-downloader から取得した生データ
        video_id: 動画ID
        video_title: 動画タイトル
    
    Returns:
        dict: 変換後のチャットデータ、または None（スキップする場合）
    """
    # viewer_engagement_message などシステムメッセージはスキップ
    message_type = raw_message.get('message_type', '')
    if message_type == 'viewer_engagement_message':
        return None
    
    # 必要なフィールドを抽出
    message_id = raw_message.get('message_id', '')
    message = raw_message.get('message', '')
    timestamp = raw_message.get('timestamp', 0)
    time_text = raw_message.get('time_text', '')
    
    # author 情報
    author = raw_message.get('author', {})
    author_name = author.get('name', '')
    author_channel_id = author.get('id', '')
    
    # money 情報（Super Chat）
    money_data = raw_message.get('money')
    money = None
    if money_data:
        money = {
            'amount': money_data.get('amount', 0),
            'currency': money_data.get('currency', '')
        }
    
    # body_background_colour（Super Chat の背景色）
    body_background_colour = raw_message.get('body_background_colour', '')
    
    # メッセージの絵文字を alias に変換
    if message:
        message = emoji.emojize(message, language='alias')
    
    # datetime を生成
    datetime_str = convert_timestamp_to_datetime(timestamp)
    
    # timestamp をマイクロ秒からミリ秒に変換
    timestamp_ms = round(timestamp / 1_000) if timestamp else 0
    
    # 出力データを構築
    output_data = {
        'id': message_id,
        'videoId': video_id,
        'videoTitle': video_title,
        'type': 'chat',
        'message_type': message_type,
        'message': message,
        'timestamp': timestamp_ms,
        'elapsedTime': time_text,
        'authorName': author_name,
        'authorChannelId': author_channel_id,
        'datetime': datetime_str,
    }
    
    # money がある場合のみ追加
    if money:
        output_data['money'] = money
    
    # body_background_colour がある場合のみ追加
    if body_background_colour:
        output_data['body_background_colour'] = body_background_colour
    
    return output_data


def process_raw_chat_file(raw_file_path: str, output_file_path: str, 
                          video_id: str, video_title: str) -> tuple[int, int]:
    """
    1つの raw chat ファイルを処理して NDJSON に変換する
    
    Args:
        raw_file_path: 入力ファイルパス
        output_file_path: 出力ファイルパス
        video_id: 動画ID
        video_title: 動画タイトル
    
    Returns:
        tuple: (処理成功件数, エラー件数)
    """
    success_count = 0
    error_count = 0
    
    with open(raw_file_path, 'r', encoding='utf-8') as infile, \
         open(output_file_path, 'w', encoding='utf-8') as outfile:
        
        for line_num, line in enumerate(infile, start=1):
            line = line.strip()
            if not line:
                continue
            
            try:
                raw_message = json.loads(line)
                converted = convert_raw_chat_to_ndjson(raw_message, video_id, video_title)
                
                if converted:
                    json.dump(converted, outfile, ensure_ascii=False)
                    outfile.write('\n')
                    success_count += 1
                    
            except json.JSONDecodeError as e:
                print(f"    [WARN] 行 {line_num}: JSON解析エラー - {e}", file=sys.stderr)
                error_count += 1
                continue
            except Exception as e:
                print(f"    [WARN] 行 {line_num}: 変換エラー - {type(e).__name__}: {e}", file=sys.stderr)
                error_count += 1
                continue
    
    return success_count, error_count


def main():
    # ディレクトリパスを環境変数から取得
    local_chat_logs_dir = os.getenv('LOCAL_CHAT_LOGS_DIR')
    if not local_chat_logs_dir:
        print("Error: LOCAL_CHAT_LOGS_DIR 環境変数が設定されていません", file=sys.stderr)
        sys.exit(1)
    
    videos_ndjson_path = os.getenv('VIDEOS_NDJSON')
    if not videos_ndjson_path:
        print("Error: VIDEOS_NDJSON 環境変数が設定されていません", file=sys.stderr)
        sys.exit(1)
    
    raw_chat_logs_dir = os.path.join(local_chat_logs_dir, 'chat_logs_raw')
    chat_logs_dir = os.path.join(local_chat_logs_dir, 'chat_logs')
    
    # ディレクトリの存在確認
    if not os.path.exists(raw_chat_logs_dir):
        print(f"Error: raw_chat_logs ディレクトリが見つかりません: {raw_chat_logs_dir}", file=sys.stderr)
        sys.exit(1)
    
    # 出力ディレクトリの作成
    if not os.path.exists(chat_logs_dir):
        os.makedirs(chat_logs_dir)
        print(f"出力ディレクトリを作成しました: {chat_logs_dir}")
    
    # 動画メタデータを読み込み
    video_metadata = load_video_metadata(videos_ndjson_path)
    
    # 処理結果のカウンター
    total_files = 0
    success_files = 0
    skip_files = 0
    error_files = 0
    
    # raw_chat_logs ディレクトリ内のファイルを処理
    print("-" * 60)
    print("チャットログの変換を開始します")
    print("-" * 60)
    
    for filename in sorted(os.listdir(raw_chat_logs_dir)):
        if not filename.endswith('.ndjson'):
            continue
        
        total_files += 1
        
        # ファイル名から video_id を抽出
        # ファイル名パターン: {video_id}.ndjson または {video_id}_raw.ndjson
        video_id = filename.replace('_raw.ndjson', '').replace('.ndjson', '')
        
        # 動画タイトルを取得
        video_title = video_metadata.get(video_id, '')
        if not video_title:
            print(f"[{total_files}] {video_id}: タイトルが見つかりません（メタデータなし）", file=sys.stderr)
        
        raw_file_path = os.path.join(raw_chat_logs_dir, filename)
        output_filename = f"{video_id}.json"
        output_file_path = os.path.join(chat_logs_dir, output_filename)
        
        # 既存ファイルのチェック（スキップ）
        if os.path.exists(output_file_path):
            print(f"[{total_files}] {video_id}: スキップ（出力ファイルが既に存在）")
            skip_files += 1
            continue
        
        print(f"[{total_files}] {video_id}: 処理中...")
        
        try:
            success_count, error_count = process_raw_chat_file(
                raw_file_path, output_file_path, video_id, video_title
            )
            
            if success_count > 0:
                print(f"  -> {success_count} 件のメッセージを変換しました: {output_filename}")
                success_files += 1
            else:
                print(f"  -> 変換対象のメッセージがありませんでした")
                # 空のファイルは削除
                if os.path.exists(output_file_path):
                    os.remove(output_file_path)
                error_files += 1
                
        except Exception as e:
            print(f"  [ERROR] ファイル処理エラー: {type(e).__name__}: {e}", file=sys.stderr)
            error_files += 1
            # エラー時は不完全なファイルを削除
            if os.path.exists(output_file_path):
                os.remove(output_file_path)
    
    # 処理結果のサマリー
    print("-" * 60)
    print(f"処理完了:")
    print(f"  総ファイル数: {total_files}")
    print(f"  成功: {success_files}")
    print(f"  スキップ: {skip_files}")
    print(f"  エラー: {error_files}")


if __name__ == '__main__':
    main()
