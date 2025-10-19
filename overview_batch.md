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
                    c.datetime (文字列):そのチャットが投稿された現実の日時 (例: 2024-10-19 17:00:05)
                    c.elapsedTime (文字列):ご要望の「動画のタイムスタンプ」です。
                    c.timestamp (整数):動画開始時点からの経過時間（ミリ秒） (例: 125000)
                    c.message (文字列):チャットの本文です (例: こんばんはー！)
                    c.author.name (文字列):投稿者の表示名です (例: ユーザーA)
                    c.id (文字列):チャットメッセージ固有のIDです。
                }
        - ファイル名
            {video_id}.json

