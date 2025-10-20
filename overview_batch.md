## 概要
ある YouTubeチャンネルのライブ動画の一覧と その ライブ動画の チャット の ログを取得したい。
データの取得には、 YouTube Data API v3 と pytchat を利用する。
このアプリの利用者は 対象のYouTubeチャンネル の オーナー ではない

## 詳細
1. get_videos.py
    - https://www.youtube.com/@Utsuro_himuro/streams から 動画の一覧を取得してテキストに保存する
        - ファイル形式
            - タブ区切り UTF-8
            - ヘッダーあり
        - カラム
            - title
            - video_url
            - thumnail_url
        - ファイル名
            - utsuro_himuro_streams.tsv

2. get_chatlog.py
    - utsuro_himuro_streams.tsv から 順に 動画のチャットリプレイを取得してJSOLファイルの保存する
        - pytchat を 利用する
        - JSON形式
            - elasticsearch 投入用 JSON
                {
                    videoId (文字列):そのチャットが投稿されたVideoのID
                    datetime (文字列):そのチャットが投稿された現実の日時 (例: 2024-10-19 17:00:05)
                    elapsedTime (文字列):ご要望の「動画のタイムスタンプ」です。
                    timestamp (整数):動画開始時点からの経過時間（ミリ秒） (例: 125000)
                    message (文字列):チャットの本文です (例: こんばんはー！)
                    authorName (文字列):投稿者の表示名です (例: ユーザーA)
                    authorChannelId (文字列):投稿者のチャンネルIDです
                    id (文字列):チャットメッセージ固有のIDです。
                }
        - ファイル名
            {video_id}.json

## 機能外要件

### elasticsearch
    Elastic Cloud
        https://my-elasticsearch-project-d32e2f.kb.ap-northeast-1.aws.elastic.cloud/app/elasticsearch/home

### chat log storage
    https://ap-northeast-1.console.aws.amazon.com/s3/get-started?region=ap-northeast-1
