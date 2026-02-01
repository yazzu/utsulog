#!/usr/bin/env python3
"""
YouTubeアーカイブ動画からチャットリプレイデータを取得するスクリプト

chat-downloaderライブラリを使用して、YouTube動画のチャットリプレイを
Rawデータとして保存します。
"""

import json
import os
import sys
from chat_downloader import ChatDownloader
from chat_downloader.errors import (
    VideoUnavailable,
    NoChatReplay,
    LoginRequired,
    ChatDownloaderError
)


def get_chat_logs(video_id: str, output_dir: str, cookies_path: str = None) -> bool:
    """
    指定された動画IDのチャットリプレイを取得して保存する
    
    Args:
        video_id: YouTubeの動画ID
        output_dir: 出力ディレクトリパス
        cookies_path: Cookieファイルのパス（オプション）
    
    Returns:
        bool: 成功した場合True、失敗した場合False
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    output_file = os.path.join(output_dir, f"{video_id}.ndjson")
    
    try:
        downloader = ChatDownloader(cookies=cookies_path)
        chat = downloader.get_chat(url, message_types=['all'])
        
        message_count = 0
        with open(output_file, 'w', encoding='utf-8') as f:
            for message in chat:
                json.dump(message, f, ensure_ascii=False)
                f.write('\n')
                message_count += 1
        
        if message_count == 0:
            print(f"  [INFO] {video_id}: チャットメッセージが0件でした", file=sys.stderr)
            # 空のファイルは削除
            os.remove(output_file)
            return False
        
        print(f"  [OK] {video_id}: {message_count}件のメッセージを保存しました -> {output_file}")
        return True
        
    except VideoUnavailable as e:
        print(f"  [ERROR] {video_id}: 動画が利用不可です (削除または非公開) - {e}", file=sys.stderr)
        return False
        
    except NoChatReplay as e:
        print(f"  [ERROR] {video_id}: チャットリプレイが存在しません - {e}", file=sys.stderr)
        return False
        
    except LoginRequired as e:
        print(f"  [ERROR] {video_id}: ログインが必要です (メンバー限定等) - {e}", file=sys.stderr)
        return False
        
    except ChatDownloaderError as e:
        print(f"  [ERROR] {video_id}: チャット取得エラー - {e}", file=sys.stderr)
        return False
        
    except Exception as e:
        print(f"  [ERROR] {video_id}: 予期しないエラー - {type(e).__name__}: {e}", file=sys.stderr)
        return False


def main():
    # 入力ファイルパス
    input_file = os.getenv('VIDEOS_NDJSON')
    
    # 出力ディレクトリ
    output_dir = os.path.join(os.getenv('LOCAL_CHAT_LOGS_DIR'), "raw_chat_logs")
    
    # Cookieファイルパス（オプション）
    cookies_path = os.getenv('YOUTUBE_COOKIES')
    if cookies_path and os.path.exists(cookies_path):
        print(f"Cookieファイルを使用します: {cookies_path}")
    else:
        cookies_path = None

    # 入力ファイルの存在確認
    if not os.path.exists(input_file):
        print(f"Error: 入力ファイルが見つかりません: '{input_file}'", file=sys.stderr)
        sys.exit(1)
    
    # 出力ディレクトリの作成
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"出力ディレクトリを作成しました: {output_dir}")
    
    # 処理結果のカウンター
    total_count = 0
    success_count = 0
    skip_count = 0
    error_count = 0
    
    # 動画リストを読み込んで処理
    print(f"動画リストを読み込み中: {input_file}")
    print("-" * 60)
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            
            try:
                video_data = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  [WARN] 行 {line_num}: 不正なJSON形式です - {e}", file=sys.stderr)
                error_count += 1
                continue
            
            url = video_data.get('video_url')
            title = video_data.get('title')
            try:
                video_id = url.split('v=')[1].split('&')[0]
            except IndexError:
                print(f"  Invalid URL: {url}")
                continue
            
            if not video_id:
                print(f"  [WARN] 行 {line_num}: video_idが見つかりません", file=sys.stderr)
                error_count += 1
                continue
            
            total_count += 1
            print(f"[{total_count}] {title} ({video_id})")
            
            # 既存ファイルのチェック（既にある場合はスキップ）
            output_file = os.path.join(output_dir, f"{video_id}_raw.ndjson")
            if os.path.exists(output_file):
                print(f"  [SKIP] ファイルが既に存在します: {output_file}")
                skip_count += 1
                continue
            
            # チャットログを取得
            if get_chat_logs(video_id, output_dir, cookies_path):
                success_count += 1
            else:
                error_count += 1
    
    # 処理結果のサマリー
    print("-" * 60)
    print(f"処理完了:")
    print(f"  総動画数: {total_count}")
    print(f"  成功: {success_count}")
    print(f"  スキップ: {skip_count}")
    print(f"  エラー: {error_count}")


if __name__ == '__main__':
    main()
