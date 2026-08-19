## 概要
ある YouTubeチャンネルのライブ動画の一覧と その ライブ動画の チャット の ログを取得したい。
データの取得には、 YouTube Data API v3 と pytchat を利用する。
このアプリの利用者は 対象のYouTubeチャンネル の オーナー ではない

## 詳細
1. get_videos.py
    - https://www.youtube.com/@Utsuro_himuro/streams から 動画の一覧を取得して videos/videos.ndjson に保存する
    - channels().list から uploads 再生リストを取得
    - playlistItems().list から uploads 再生リストの全ての動画IDを取得
    - videos().list から 動画の詳細を取得
    - videos.ndjson に保存する
        {
            'title': title,
            'video_url': video_url,
            'thumbnail_url': thumbnail_url,
            'publishedAt': published_at,
            'actualStartTime': actualStartTime
        }

2. get_chatlogs_raw.py
    ## 入力データ仕様
    - ファイルパス: `videos.ndjson`
    - フォーマット: NDJSON
    - 各行の構造例: `{"video_id": "VIDEO_ID_HERE", "title": "..."}`
    - この中の `video_id` を使用して、YouTubeのURL (`https://www.youtube.com/watch?v={video_id}`) を構築する。

    ## 出力データ仕様
    - 保存ディレクトリ: `raw_chat_logs/` (存在しない場合は作成)
    - ファイル名: `{video_id}.ndjson`
    - フォーマット: NDJSON (JSON Lines)
    - データ内容: `chat-downloader` が取得した各チャットメッセージの辞書オブジェクト（Rawデータ）をそのまま保存する。スパチャ、ステッカー、通常のチャットなど全てのタイプを含めること。

    ## 処理フロー
    1. **ライブラリの準備:**
    - `chat_downloader` (`ChatDownloader`) をインポートする。

    2. **動画ごとのループ処理:**
    - `videos/videos.ndjson` を読み込み、各 `video_id` について以下の処理を行う。
    
    - **チャット取得の実行:**
        - `ChatDownloader().get_chat(url)` メソッドを使用する。
        - URLは `https://www.youtube.com/watch?v={video_id}`。
        - **ジェネレータ処理:** 取得したメッセージをループで回し、即座にファイルへ1行ずつ書き込む（メモリ不足を防ぐため、全リストをメモリに保持しないこと）。
    
    3. **保存処理の実装詳細:**
    - ファイルオープン時のモードは、途中再開などを考慮するなら追記モード(`a`)や、上書きモード(`w`)を適切に選定するが、今回はシンプルに新規作成(`w`)で良い。
    - `json.dumps(message, ensure_ascii=False)` を使用して書き込むこと。

3. convert_chat_to_ndjson.py
    - videos/videos.ndjson から videoId, title を取得する
    - LOCAL_CHAT_LOGS_DIR/raw_chat_logs: rawチャットログの保存先
    - LOCAL_CHAT_LOGS_DIR/chat_logs: NDJSONチャットログの保存先
    - raw_chat_logsから順にファイルを読み込んで、chat_logsにNDJSON形式で保存する
    - JSON ファイルの例
        {
            "id": c.message_id
            "videoId": videoId,
            "videoTitle": title,
            "type": "chat", -- fixed value
            "message_type": c.message_type,
            "message": emoji.emojize(c.message, language='alias'), # emoji を alias に変換する
            "timestamp": c.timestamp,
            "elapsedTime": c.time_text,
            "authorName": c.author.name,
            "authorChannelId": c.author.id,
            "datetime": fromtimestamp(c.timestamp, tz=timezone.jst).strftime('%Y-%m-%d %H:%M:%S'),
            "money": {
                "amount": c.money.amount,
                "currency": c.money.currency
            },
            body_background_colour: c.body_background_colour
        }

4. import_videos.py (旧 get_videos.py の後続処理として実行)
    - videos.ndjson の内容を Elasticsearch の `videos` インデックスに登録する
    - **変更点:** インデックスの全削除を行わず、`_bulk` API の `update` アクションと `doc_as_upsert` オプションを使用して、既存のドキュメント（処理ステータスなど）を維持したまま動画情報を更新する。
    - `videoId` を Elasticsearch のドキュメント ID (`_id`) として使用する。

5. dl_video.py
    - videos.ndjson から 順に 動画ファイルをダウンロードして保存する
        - yt-dlp を 利用する
        - 画質は 360p
        - 音声は ソース
        - ファイル名は {actualStartTime}_[{videoId}]_{title}
        - title は pathvalidate で sanitize_filename する
        - 保存先は 環境変数 VIDEOFILES_DIR
        - 保存先に同名ファイルがある場合は スキップ

6. gen_thumbnails.py
    - Elasticsearch と連携して、サムネイル作成が必要な動画のみを処理する
    - **処理フロー:**
        1. Elasticsearch から `thumbnail_created: true` でない動画IDのリストを取得する。
        2. 対象の動画ファイルに対してサムネイル生成（ffmpeg）を行う。
        3. 生成完了後、Elasticsearch の該当ドキュメントを `thumbnail_created: true` に更新する。

7. upload_thumbnails.py
    - Elasticsearch と連携して、S3へのアップロードが必要な動画のみを処理する
    - **処理フロー:**
        1. Elasticsearch から `thumbnail_created: true` かつ `thumbnail_uploaded: true` でない動画IDリストを取得する。
        2. 対象の動画IDに対応するサムネイル画像ファイル（`{video_id}_*.webp`）を検索し、S3にアップロードする。
        3. アップロード完了後、Elasticsearch の該当ドキュメントを `thumbnail_uploaded: true` に更新する。

8. vtt_to_csv.py
    - vttファイルとvideos.ndjsonファイルをjsonndファイルに変換する
    - vttファイル名： {datetime}_{videoId}_{title}_fixed.txt
        - example: 20251130061527_[M83ZGI3ZuaA]_【女剣士アスカ見参！】今度こそ何かのダンジョンをクリアさせてくれ【風来のシレン外伝】_fixed.vtt
    - videos.ndjsonファイル名：videos.ndjson
        - example
            {"title": "【女剣士アスカ見参！】今度こそ何かのダンジョンをクリアさせてくれ【風来のシレン外伝】", "video_url": "https://www.youtube.com/watch?v=M83ZGI3ZuaA", "thumbnail_url": "https://i.ytimg.com/vi/M83ZGI3ZuaA/hqdefault.jpg", "publishedAt": "20251130061527", "actualStartTime": "20251130042631"}
    - JSONNDファイル名: {basename}_vtt.json
        - example: 20251130061527_[M83ZGI3ZuaA]_【女剣士アスカ見参！】今度こそ何かのダンジョンをクリアさせてくれ【風来のシレン外伝】_vtt.json
    - JSONNDファイルの例
        {
            "videoId": vtt.filename.videoId,
            "videoTitle": videos.ndjson.title,
            "datetime": videos.ndjson.actualStartTime + vtt.datetime,
            "elapsedTime": vtt.datetime,
            "timestamp": datetime to unixtime milliseconds,
            "message": vtt.message,
            "type": "transcript", -- fixed value
            "authorName": "@Utsuro_himuro", -- fixed value
            "authorChannelId": "UC64MV1Dfq3prs9CccXg09rQ", -- fixed value
            "id": generated 40 digit hash
        }
    - 同名のJSONNDファイルが存在する場合は、スキップする

9. patch_v3_chatlogs.py
    - LOCAL_CHAT_LOGS_DIR/chat_logs: チャットログの保存先
    - LOCAL_CHAT_LOGS_DIR/chat_logs_processed: チャットログの処理済みファイルの保存先
    - チャットログの保存先JSON に 固定値のフィールド "type": "chat" を追加して、 処理済みファイルの保存先に複製する
    - "message_type": "ticker_paid_message_item" は 除外

