1. 動画名を修正するスクリプト patch_videoname.py
- VIDEOS_NDJSON_PATH: データを格納するNDJSONファイルのパス
- VIDEOFILES_DIR: 動画ファイルを格納するディレクトリのパス
- 修正前ファイル名：
    {publishedAt}_[{video_id}]_{sanitized_title}.mp4
- 修正後ファイル名：
    {actual_start_time}_[{video_id}]_{sanitized_title}.mp4

2. mp3名を修正するスクリプト patch_audioname.py
- VIDEOS_NDJSON_PATH: データを格納するNDJSONファイルのパス
- AUDIOS_DIR: mp3ファイルを格納するディレクトリのパス
- 修正前ファイル名：
    {publishedAt}_[{video_id}]_{sanitized_title}.mp3
- 修正後ファイル名：
    {actual_start_time}_[{video_id}]_{sanitized_title}.mp3
- 修正後ファイルと同名のファイルがあった場合は、修正前ファイルを削除する

3. 未終了ライブ配信をElasticsearchから削除するスクリプト remove_unfinished_lives.py
- 対象条件: `isLive=true` かつ `actualEndTime` が存在しない動画
- `ELASTICSEARCH_URL`, `VIDEOS_INDEX_NAME` を使用する
- 認証が必要な場合は `ELASTICSEARCH_ADMIN`, `ELASTICSEARCH_PASSWORD` を使用する
- CA証明書が必要な場合は `ELASTICSEARCH_CA` を使用する
- デフォルトは候補の表示だけで、削除しない

```bash
python patch_script/remove_unfinished_lives.py
```

- 表示された候補を確認後、件数を指定して削除する。候補件数が変化していた場合は削除せず終了する

```bash
python patch_script/remove_unfinished_lives.py --execute --expected-count 2
```

- 削除後に `get_videos.py` と `import_videos.py` を実行する。対象動画は配信終了後に
  `actualEndTime` が設定されれば、次回の収集で再登録される
