## 概要
ある YouTubeチャンネルのライブ動画の一覧と その ライブ動画の チャット の ログを取得したい。
データの取得には、 YouTube Data API v3 と pytchat を利用する。
このアプリの利用者は 対象のYouTubeチャンネル の オーナー ではない

## 詳細
1. get_videos.py
    - https://www.youtube.com/@Utsuro_himuro/streams から 動画の一覧を取得して videos/videos.ndjson に保存する
    - 既存の処理と同じ

2. import_videos.py (旧 get_videos.py の後続処理として実行)
    - videos.ndjson の内容を Elasticsearch の `videos` インデックスに登録する
    - **変更点:** インデックスの全削除を行わず、`_bulk` API の `update` アクションと `doc_as_upsert` オプションを使用して、既存のドキュメント（処理ステータスなど）を維持したまま動画情報を更新する。
    - `videoId` を Elasticsearch のドキュメント ID (`_id`) として使用する。

3. dl_video.py
    - videos.ndjson から 順に 動画ファイルをダウンロードして保存する
        - yt-dlp を 利用する
        - 画質は 360p
        - 音声は ソース
        - ファイル名は {publishedAt}_[{videoId}]_{title}
        - title は pathvalidate で sanitize_filename する
        - 保存先は 環境変数 VIDEOFILES_DIR
        - 保存先に同名ファイルがある場合は スキップ

4. gen_thumbnails.py
    - Elasticsearch と連携して、サムネイル作成が必要な動画のみを処理する
    - **処理フロー:**
        1. Elasticsearch から `thumbnail_created: true` でない動画IDのリストを取得する。
        2. 対象の動画ファイルに対してサムネイル生成（ffmpeg）を行う。
        3. 生成完了後、Elasticsearch の該当ドキュメントを `thumbnail_created: true` に更新する。

5. upload_thumbnails.py
    - Elasticsearch と連携して、S3へのアップロードが必要な動画のみを処理する
    - **処理フロー:**
        1. Elasticsearch から `thumbnail_created: true` かつ `thumbnail_uploaded: true` でない動画IDリストを取得する。
        2. 対象の動画IDに対応するサムネイル画像ファイル（`{video_id}_*.webp`）を検索し、S3にアップロードする。
        3. アップロード完了後、Elasticsearch の該当ドキュメントを `thumbnail_uploaded: true` に更新する。

## 機能外要件

### elasticsearch
    Elastic Cloud
        https://my-elasticsearch-project-d32e2f.kb.ap-northeast-1.aws.elastic.cloud/app/elasticsearch/home

### chat log storage
    https://ap-northeast-1.console.aws.amazon.com/s3/get-started?region=ap-northeast-1
