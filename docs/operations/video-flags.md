# 共通動画リストの種別・会員限定情報（Issue #1 / #2）

## 変更前の影響調査

`VIDEOS_NDJSON` と `VIDEOS_INDEX_NAME`（運用上 `videos_v3`）の用途を調査した。

| 利用側 | 共通リスト拡張の影響と対応 |
| --- | --- |
| `get_comments.py` / `import_comments.py` | 元から種別で除外していない。通常投稿も入力に入ることでコメント収集対象になる。変更不要。取得対象数・API呼び出し数は増える。 |
| `get_chatlogs.py` / `get_chatlogs_raw.py` | 全動画を処理すると通常投稿への無駄なアクセスや配信中の継続取得が起きる。`isLive is True` かつ `actualEndTime` がある動画に限定。 |
| `dl_video.py` / `gen_empty_videofiles.py` | 開始日時だけの条件では配信中も対象になる。終了済みライブに限定し、既存ファイル名と字幕の時刻基準を維持。 |
| `gen_thumbnails.py` | 未処理検索の1000件枠が通常投稿等で埋まる可能性がある。終了済みライブに限定。 |
| `conv_audio.py` / `vtt_to_csv.py` / チャット変換 / `upload_thumbnails.py` | 既存ファイルまたはメタデータの参照が入口。通常投稿の公開日を配信開始日時に代入しないため、ライブ由来の時刻計算は変わらない。 |
| `api/main.py` の `/videos` → frontendの動画フィルター | チャット検索用の一覧。終了済みライブで絞り、既存の表示・ソート・レスポンス形式を維持。移行中は `isLive` 未設定かつ開始日時のある旧収集データも表示する。旧収集器が終了済みライブだけを保存していたことに基づく互換条件で、一般的な種別判定ではない。 |
| `utsulog-stamp`（別リポジトリ） | 全種別が対象。`membersOnly=true` の除外は別軸。今回このリポジトリの画面・デプロイは変更しない。 |

ライブ専用バッチは未設定を推測しない。新コードでの再収集・投入後に実行する。

## フィールド契約と判定根拠

- `isLive`: [YouTube Data API videos](https://developers.google.com/youtube/v3/docs/videos#liveStreamingDetails) に `part=snippet,liveStreamingDetails` を要求し、成功した動画リソースに `liveStreamingDetails` があれば `true`、なければ `false`。配信予定・配信中・アーカイブを含む由来の判定。`snippet.liveBroadcastContent=none` はアーカイブ判定に使わない。
- `actualStartTime` / `actualEndTime`: APIの実時刻をJSTの14桁文字列にする。存在しない場合は `null`。通常投稿に公開日時を流用しない。
- `membersOnly`: [公式動画リソース](https://developers.google.com/youtube/v3/docs/videos) に会員限定専用のフィールドはない。`status.privacyStatus` やチャット取得失敗を判定根拠にしない。
- 補完元: Cookieを指定せず `https://www.youtube.com/watch?v=ID&hl=en` を取得し、そのページの `ytInitialPlayerResponse.playabilityStatus` を読む。動画・音声本体はダウンロードしない。
- `true`: 対象プレイヤーが `UNPLAYABLE` / `LOGIN_REQUIRED` で、reasonまたはerrorScreenのreason/subreasonにチャンネル会員限定を明示する英語メッセージがある。対応する文言は `batch/video_membership.py` の固定条件を参照。タイトルや説明文、関連動画は判定に使わない。
- `false`: 対象IDに一致する `videoDetails.videoId` と、匿名での `playabilityStatus.status=OK` を確認できた場合。
- 未判定: NDJSONは `membersOnly: null`。通信失敗・同意画面・年齢/地域制限・削除/非公開・未知のページ形式は `false` にしない。Elasticsearch投入時にnullフラグを取り除くため、既存の確定値を保持する。新規動画ではフィールド欠落となる。`isLive` の欠落/nullも同様に既存値を維持する。
- `membersOnlyEvidence` と `membersOnlyCheckedAt` は**最新の判定試行**の根拠コードとUTC時刻。未判定なら根拠コードが `watch_player_unknown` / `watch_player_missing` / `watch_fetch_or_parse_failed` 等になる。保持された過去の確定値の確認時刻ではない。
- `videoDetailsStatus=unavailable`: APIが成功しても対象IDが返らなかった状態。フラグを推測せず、既存タイトル・時刻・種別を投入時に上書きしない。NDJSONにはコメント処理用として従来のタイトル等を残す。

動画ページは非公式の補完元であり形式・文言が変わりうる。未知の応答は未判定に倒す。再収集は既知フラグも毎回確認するので、会員限定→一般公開と逆方向の変更を反映できる。ページ取得は動画ごとに1回、タイムアウト20秒のため、従来より収集時間とリクエスト数が増える。

## 再収集・バックフィル

対象環境の既存Compose設定を使う。`ELASTICSEARCH_URL`、`VIDEOS_INDEX_NAME=videos_v3`、認証/CA、YouTube APIキー、保存先ボリュームがその環境を指すことを確認する。稼働中の同じバッチと重複実行しない。

```sh
# 新しい収集器で、uploads・従来NDJSON・既存インデックスのIDの和集合を再取得する。
docker compose run --rm --no-deps batch python batch/get_videos.py --include-index
# 新規/既存インデックスのmappingを追加した後、既存の_idへ部分更新する。
docker compose run --rm --no-deps batch python batch/import_videos.py
# 通常投稿を含むコメントを収集して投入する。
docker compose run --rm --no-deps batch python batch/get_comments.py
docker compose run --rm --no-deps batch python batch/import_comments.py
```

`--include-index` は既存インデックスがある場合に使用する。初回構築では付けずに取得→投入する。インデックス読み取りはscrollで全件を走査し、1000件で打ち切らない。インデックス読取失敗は処理を中断する。

通常実行も「uploads＋既存NDJSON」のIDを再取得する。初回バックフィルで取り込んだインデックスのみのIDは、以後もNDJSONに残り再試行対象になる。取得不能IDは消さず、判定不能として保持する。APIリクエスト自体の失敗ではNDJSONを置き換えない。出力は一時ファイルからatomic replaceする。

特定IDを再確認する場合は、通常バッチの入力を小さなリストに置き換えないよう別ファイルを使う。

```sh
docker compose run --rm --no-deps -e VIDEOS_NDJSON=/app/videos/video-flags-check.ndjson batch \
  python batch/get_videos.py --video-id qmQ4VJ5TfxY --video-id qsOw7Q8WJQA
docker compose run --rm --no-deps -e VIDEOS_NDJSON=/app/videos/video-flags-check.ndjson batch \
  python batch/import_videos.py
```

インデックスを削除・再作成しない。`isLive` / `membersOnly` はboolean、`actualEndTime` はkeywordとして明示マッピングする。既存に互換性のないmappingがあれば投入前に停止する。`update` + `doc_as_upsert` と同じ動画IDを使い、収集器が処理ステータスを再出力しないことで保持する。Bulkの部分エラーでも実行は失敗終了し、再実行可能。

未判定の再試行は同じコマンドを再実行する。バックフィル後は `_mapping`、対象2動画の `_doc/ID`、未設定件数、`membersOnlyEvidence` のunknown件数を確認する。未設定を一括でfalseにするスクリプトは使用しない。

## 検証（2026-09-13）

実YouTube APIと匿名動画ページから取得した結果:

| 動画ID | isLive | membersOnly | 開始 / 終了（JST） | 会員判定根拠 |
| --- | --- | --- | --- | --- |
| `qmQ4VJ5TfxY` | true | true | 20250216210104 / 20250217011729 | `watch_player_members_only` |
| `qsOw7Q8WJQA` | false | false | null / null | `watch_player_anonymous_playable` |

この2レコードを開発Elasticsearchの専用一時インデックスへ実投入し、booleanマッピング・2回投入で2件・処理ステータス保持・双方向の公開範囲変更・null再試行時の確定情報保持を確認した。一時インデックスは検証後に削除した。

通常投稿 `qsOw7Q8WJQA` は共通NDJSONを `get_comments.load_videos` で読み、実APIから50件のコメントを取得した。リポジトリのkuromoji入りElasticsearchイメージの一時コンテナで、`import_comments` のmappingとBulk生成経路を使い50件の投入を確認した（別アプリの開発ESはkuromojiなしのため、本リポジトリの構成で再検証）。検証用インデックスは削除済み。

batch/APIは実ES連携を含め29テスト通過。frontendは5テスト通過、production build成功。

再現可能な回帰テスト:

```sh
PYTHONPATH=api:batch pytest -q batch/tests api/tests
# 開発ESのみを指定する。一意なテストインデックスを作成し、終了時に削除する。
PYTHONPATH=api:batch VIDEO_TEST_ES_URL=http://127.0.0.1:9200 pytest -q batch/tests api/tests
npm --prefix frontend test
npm --prefix frontend run build
```

本番へのコード反映・全件バックフィル、および別リポジトリのスタンプ画面での一覧/押印確認は未実施。上記コマンドは本番で実行済みという意味ではない。
