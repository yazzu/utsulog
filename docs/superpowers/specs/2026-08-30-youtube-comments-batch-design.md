# YouTubeコメント取得〜ES投入バッチ 設計

## 位置づけ

`docs/comment-index-schema.md`で定義された`youtube-comments_v1`インデックスに対し、`utsulog`プロジェクト側で実際にコメントを取得してElasticsearchへ投入するバッチパイプラインを新設する。既存の`get_videos.py`→`get_chatlogs.py`(または`get_chatlogs_raw.py`+`convert_chat_to_ndjson.py`)→`import_chatlogs.py`という確立済みパイプラインと並列する、コメント専用の新規サブシステムとして構築する。

## 全体構成

```
videos/videos.ndjson
    │
    ▼
batch/get_comments.py ──(YouTube Data API v3: commentThreads.list / comments.list)
    │
    ▼
${LOCAL_COMMENTS_DIR}/comments/{video_id}_comments.ndjson
    │
    ▼
batch/import_comments.py ──(_bulk index、id指定で洗い替え)
    │
    ▼
Elasticsearch: youtube-comments_v1
    │
    ├─ 成功 → ${LOCAL_COMMENTS_DIR}/comments_processed/
    └─ 失敗 → ${LOCAL_COMMENTS_DIR}/comments_error/
```

取得(API呼び出し+スキーマ変換)と投入の2段階構成とする。YouTube Data APIのレスポンスは元々構造化されているため、チャットログのような「raw保存→変換」の中間ステップは設けない。

## get_comments.py 仕様

### 入力

- `videos/videos.ndjson`(`get_videos.py`の出力。既存の`get_chatlogs_raw.py`と同じ読み込み方式で`video_url`から`video_id`を抽出する)

### 対象範囲

- `videos.ndjson`に含まれる全動画を対象とする。ESの既存チャットデータとの突合は行わない。

### 取得ロジック

1. `googleapiclient.discovery.build`(`get_videos.py`と同じ)で`YOUTUBE_API_KEY`を用いてYouTubeクライアントを生成する。
2. 動画ごとに`commentThreads().list(part='snippet,replies', videoId=video_id, maxResults=100)`を`pageToken`でページングしながら全件取得する。
3. 各スレッドについて、`snippet.topLevelComment.snippet`をスキーマ形式のトップレベルコメント(`isReply: false`, `parentId: null`)に変換する。
4. `snippet.totalReplyCount`が埋め込み`replies.comments`の件数より多い場合、`comments().list(parentId=threadId, maxResults=100)`を`pageToken`でページングし、不足分の返信を追加取得する。返信は`isReply: true`、`parentId`にスレッドの(トップレベルコメントの)IDを設定する。
5. 1動画分の全コメントをメモリ上のリストに集約してから、最後にまとめて1ファイルへ書き出す(ページング途中でのファイル部分書き込みは行わない。理由は下記「全件再取得方針とエラー処理」を参照)。

### フィールド変換

`docs/comment-index-schema.md`のスキーマに従う。主な変換:

- `id`: コメントのYouTube API ID(トップレベル・返信とも、API側が返すグローバル一意なIDをそのまま使用する。加工しない)
- `message`: `textOriginal`をそのまま保存する。絵文字の`:alias:`変換は行わない(チャットログとは異なる方針)。
- `publishedAt`: API の値(UTC ISO8601)をそのまま保持。
- `datetime`: `publishedAt`をJST(`Asia/Tokyo`)に変換した`YYYY-MM-DD HH:MM:SS`文字列(チャットログの変換ロジックを流用)。
- `timestamp`: `publishedAt`をエポックミリ秒に変換。
- `authorName` / `authorChannelId`: `snippet.authorDisplayName` / `snippet.authorChannelId.value`。
- `likeCount`: `snippet.likeCount`。
- `isReply` / `parentId`: 上記の通り。
- `videoId` / `videoTitle`: `videos.ndjson`の値を非正規化して埋め込む。

### 出力

- 保存先: `${LOCAL_COMMENTS_DIR}/comments/{video_id}_comments.ndjson`(ファイル名にチャットログとの混在を避けるため`_comments`サフィックスを付与)
- フォーマット: NDJSON(スキーマ準拠の1コメント1行)
- 全件再取得方針のため、既存ファイルがあっても上書きする(スキップしない)。
- 対象動画のコメントが0件の場合はファイルを作成しない(既存の空ファイル削除パターンを踏襲)。

## import_comments.py 仕様

`batch/import_chatlogs.py`をベースに、以下の差分で実装する。

### 環境変数

- `COMMENTS_INDEX_NAME`(デフォルト: `youtube-comments_v1`)
- `LOCAL_COMMENTS_DIR`(新規。`docker-compose.yml`のbatchサービスにも追加する)

### インデックス作成

`create_index_if_not_exists`と同様の存在確認+作成ロジックを流用するが、マッピングはチャットログの絵文字カスタムアナライザーを設定しない。`message`フィールドは`kuromoji_tokenizer`を使った標準的な日本語検索用アナライザーのみを設定する(絵文字変換を行わないため専用アナライザーは不要)。

### Bulk投入

既存`import_chatlogs.py`は`_bulk`の`index`アクションで`_id`を指定していないため、実行のたびに新規ドキュメントとして追加されてしまう。コメント投入では全件再取得+上書き方針を成立させるため、`_bulk`の`index`アクションに`_id`としてドキュメントの`id`フィールドを明示的に指定し、同一IDのドキュメントは上書きされるようにする。これが既存実装との主要な差分となる。

### ファイル移動

処理成功時は`${LOCAL_COMMENTS_DIR}/comments_processed/`、失敗時は`${LOCAL_COMMENTS_DIR}/comments_error/`に移動する(既存パターン踏襲)。

## 全件再取得方針とエラー処理

- コメントは配信後も追加され続けるため、差分管理は行わず、実行のたびに対象動画の全コメントを再取得して上書きする。
- `commentThreads.list`が`commentsDisabled`(403)を返す動画は正常系として扱い、ログ出力してスキップする(ファイルは作成しない)。
- `quotaExceeded`等その他のAPIエラーが発生した場合、その動画の取得を中断してログ出力し、次の動画の処理を継続する。取得途中のデータは破棄し、部分的な内容でファイルを書き出さない(次回実行時に全件取得からやり直すことで整合性を保つ)。
- YouTube側で削除されたコメントは、次回全件再取得時にAPIレスポンスへ含まれなくなるが、ES側の既存ドキュメントは自動削除されない(indexアクションによる上書きのみで、差分削除は行わない)。スタンプ判定は`authorChannelId`の集合にのみ依存するため、この残留は実害がないと判断し、本設計ではスコープ外とする。

## run_batch.sh / docker-compose.yml への変更

- `run_batch.sh`の`import_chatlogs.py`実行ステップの直後に、以下を追加する:
  ```
  echo "Running get_comments.py..."
  python batch/get_comments.py
  echo "Running import_comments.py..."
  python batch/import_comments.py
  ```
- `docker-compose.yml`のbatchサービス環境変数に`LOCAL_COMMENTS_DIR`(例: `/app/comments`)を追加する。

## docs/comment-index-schema.md への修正

- `id`フィールドの説明(現行39行目)を「返信コメントの場合は`{parentCommentId}_{replyId}`のように親IDと組み合わせて一意にする」から「返信コメントも含め、YouTube Data APIが返すグローバルに一意なコメントIDをそのまま使用する」に修正する。

## テスト方針

`batch/`配下の既存スクリプト群(外部API依存)と同様、自動テストは作成せず、実際の動画IDを用いた手動実行で動作確認する既存慣習に合わせる。

## スコープ外

- YouTube側で削除されたコメントのES側からの削除(上記の通り実害なしと判断)
- チャット・コメント横断のスタンプ判定ロジック自体の実装変更(`docs/comment-index-schema.md`側の既存記載通り、将来utsulog-stamp側で対応)
- コメントの絵文字検索対応(チャットログの`emoji_analyzer`相当の仕組みは今回導入しない)
