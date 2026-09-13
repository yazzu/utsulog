# Issue #1・#2 本番反映計画

この文書は実行計画。現時点で本番反映は行っていない。
仕様・影響調査は [video-flags.md](video-flags.md) を参照。

## 反映順序

1. 開発機で対象変更をレビュー・コミットし、GitHubへpush／PRをマージする。対象コミットSHAを記録する。
2. Piの定期バッチを停止し、実行中のバッチの終了を待つ。設定、データ、旧コード／イメージ、復旧手段を確認する。
3. 本番APIへ先に `/videos` の絞り込みを反映する。
4. Piで対象コミットを取得し、batchイメージをビルドする。
5. 別NDJSONで報告動画2本を収集・検査してから、本番インデックスへ部分投入する。
6. 通常投稿のコメントだけを独立した保存先で収集・投入し、両アプリを確認する。
7. 全動画を再収集・投入する。ライブ処理・全コメント収集はここではまだ起動しない。
8. 確認後に定期バッチを再開し、初回を監視する。

APIはPiのbatchとは別の反映先。リポジトリの `api/deploy_prod.sh` はAWS Lambda `utsulog-api-lambda` を対象にlinux/amd64イメージをビルドし、コードと `.env.prod` 由来の環境変数を更新する。Piから機械的に実行せず、通常APIをデプロイする端末とAWS権限で実行する。今回frontendのビルド・デプロイは不要。

## 1. リリース準備（開発機）

今回の修正は計画作成時点では未コミット。Piでpullする前にGitHubで取得可能にする。

- `git diff` をレビューし、今回のソース・テスト・運用文書だけをコミットする。別作業の変更や秘密情報を含めない。
- GitHubのPRで変更と検証結果を確認し、マージ後の完全なSHAを記録する。
- 本番APIとPiのbatchが同じ変更を含むことをSHAで確認する。
- 既存テスト結果: batch/API 29件、frontend 5件とビルド成功。実APIで報告動画の種別・会員判定とコメント50件の取得／一時ES投入を確認済み。

## 2. Piの現状確認と保全

PiのCodexに以下を調べさせ、秘密の値は出力せず、確認結果のみ記録する。

- リポジトリの場所、ブランチ、SHA、未コミット変更。
- cron / systemd timer等、実際の定期起動経路と実行ユーザー。対象ジョブのみ一時停止する。他のジョブを変更しない。
- 実行中のbatch。正常終了を待ち、収集途中での同時実行を避ける。
- 本番で使うComposeファイル・envファイル・project名。`.env.prod` をPiでも使うとは限らない。
- batchコンテナから見た動画／コメント／処理済みディレクトリの永続マウント、空き容量、所有者・権限。
- Elasticsearch接続先が本番であること、動画インデックスが `videos_v3` であること、コメントインデックス名・認証・CA。
- `youtube-comments_v1` が未作成なら、kuromojiを利用できることとインデックス作成権限。既存ならmessageのmappingも確認。

停止後に旧SHA、旧batchイメージID、現行NDJSON、コメントの保存／処理済み状態を保全する。認証情報を含むバックアップはアクセス権を制限する。

Elasticsearchは既存のsnapshot等の復旧手段と最終成功時刻を確認する。S3ファイルバックアップがESインデックスの復元にも使えるとは仮定しない。変更前の `videos_v3` のmapping・件数・処理ステータスのサンプル、対象2動画の有無と `_source` を記録する。

## 3. 本番APIの先行反映

- 現行Lambdaの解決済みイメージURI／バージョン、設定を記録する。
- 既存のAPIデプロイ手順で今回の `api/main.py` を反映する。
- `api/deploy_prod.sh` を使う場合は、実行前に本番Lambda名、AWSアカウント、`.env.prod` と現在のLambda設定の差分を確認する。このスクリプトはコードだけでなく環境変数も更新する。
- APIが応答し、従来の配信一覧・チャット検索が動くことを確認する。`isLive` 未設定の旧アーカイブは互換条件で表示される。

ここで失敗した場合はデータ投入へ進まない。現行のAPIイメージに戻して調査する。

## 4. Piのコード更新とビルド

未コミット変更がある場合は強制resetせず、内容を確認して保全する。通常の本番ブランチ運用なら以下を使う。

```sh
git status --short
git fetch origin
git pull --ff-only
git rev-parse HEAD
```

出力SHAが承認したリリースと一致することを確認する。別ブランチ・別コミットが最新ならそのまま実行しない。

以下は **Bash** で、既存本番と同じCompose指定を配列 `dc` に設定して実行する。Piの現状調査で正しい方を選ぶ。

```bash
# 例A: 本番がリポジトリの .env を使っている場合
dc=(docker compose)
# 例B: 本番が明示的なenvファイルを使っている場合は、上の代わりに設定する
# dc=(docker compose --env-file /実際の本番envファイル)
# 独自 -f / -p がある運用では、その指定も既存起動方法に合わせる。

"${dc[@]}" build batch
```

batchはホストコードを `/app` にマウントする構成なので、コード更新時点から次の実行へ影響する。定期ジョブを止めてから更新する。

## 5. 報告動画2本の先行確認

新しいファイル名を使い、既存の共通NDJSONを置き換えない。以下の `/app/videos` は現行Composeのコンテナ内パス。

```bash
rollout_id=$(date -u +%Y%m%dT%H%M%SZ)
check_ndjson="/app/videos/issue12-${rollout_id}.ndjson"

"${dc[@]}" run --rm --no-deps -e VIDEOS_NDJSON="$check_ndjson" batch \
  python batch/get_videos.py --video-id qmQ4VJ5TfxY --video-id qsOw7Q8WJQA
```

Pi上のCodexに、このファイルを対応する永続マウントから読み、以下を確認させる。

| ID | 2026-09-13確認時の期待値 |
| --- | --- |
| `qmQ4VJ5TfxY` | isLive=true、membersOnly=true、開始・終了日時あり |
| `qsOw7Q8WJQA` | isLive=false、membersOnly=false、開始・終了日時null |

公開範囲は変わりうるので、値が違えば現在の判定根拠を確認する。nullやunknownを期待値に手修正しない。PiからのYouTubeアクセスが拒否される場合は、原因を調べて再取得する。

確認後に投入する。

```bash
"${dc[@]}" run --rm --no-deps -e VIDEOS_NDJSON="$check_ndjson" batch \
  python batch/import_videos.py
```

本番ESでboolean mapping、対象2件の値、既存処理ステータスの維持を確認する。動画IDが `_id` なので再実行しても同じ2件を更新する。通常投稿がutsulogのチャット検索用一覧に出ず、utsulog-stampの通常動画一覧には入ることを確認する。会員限定動画はスタンプ側の既存フラグ対応で除外されることを確認する。

## 6. 対象通常投稿のコメント確認

Codexに先行確認NDJSONから `qsOw7Q8WJQA` の1行だけを選んだ別NDJSONを作成させる。以下の変数にはそのコンテナ内ファイルパスを設定する。

```bash
# 実際に作成した1行のファイル
comment_video_ndjson="/app/videos/issue12-comments-${rollout_id}.ndjson"
comment_workdir="/app/comments/issue12-${rollout_id}"

"${dc[@]}" run --rm --no-deps \
  -e VIDEOS_NDJSON="$comment_video_ndjson" -e LOCAL_COMMENTS_DIR="$comment_workdir" batch \
  python batch/get_comments.py
```

ログのエラー件数が0、出力ファイルが存在し、レコードが対象動画のものであることを確認する。以前は50件だったが現在のコメント数との完全一致を前提にしない。

```bash
"${dc[@]}" run --rm --no-deps -e LOCAL_COMMENTS_DIR="$comment_workdir" batch \
  python batch/import_comments.py
```

専用保存先なので他動画の未投入ファイルを一緒に処理しない。コメントIDを `_id` として投入するため既存の個別補完分とも重複しない。ESの対象動画のコメント件数・サンプルと、スタンプ側の既知のコメント投稿者の押印を確認する。

**コメント処理は終了コードだけで成功判定しない。** 現行 `get_comments.py` は動画ごとのエラーをログに記録して続行し、`import_comments.py` も失敗ファイルを移動する経路がある。エラー件数、`comments_error`、実ESの件数を確認する。

## 7. 全件バックフィル

先行確認を通過してから、通常の共通NDJSONを再生成する。

```bash
"${dc[@]}" run --rm --no-deps batch python batch/get_videos.py --include-index
```

この段階は動画ページへ動画数分のアクセスが発生する。収集時間は従来より増える。NDJSON件数、ID重複なし、isLiveのtrue/false件数、membersOnlyのtrue/false/null件数、API未取得件数を確認する。API成功なのに全件unknownなど、先行確認と大きく異なる場合は投入前に調査する。

```bash
"${dc[@]}" run --rm --no-deps batch python batch/import_videos.py
```

確認事項:

- 既存動画IDが失われていない。新規動画分だけ件数が増える。
- `isLive` / `membersOnly` のmappingがboolean。
- 既存アーカイブは `isLive=true`。通常投稿はfalse。予定・配信中の動画はtrueで、終了日時は未設定。
- 未取得／判定不能動画の過去の確定情報が維持されている。
- `thumbnail_created` 等の既存処理ステータスが維持されている。
- APIの配信一覧・既存チャット検索・スタンプの一覧／会員除外が想定どおり。

他の通常投稿のコメントを直ちに補完するなら `get_comments.py` → ログ検査 → `import_comments.py` を個別実行する。次回定期実行へ回す場合は、その時点まで他動画のコメント補完は未完了として記録する。

## 8. 定期実行再開と完了条件

- 停止した対象スケジュールのみ元に戻す。
- 初回実行で通常投稿や未終了配信がチャット取得・動画保存に入らないことを確認する。
- 会員判定のunknown件数、YouTube APIエラー、処理時間、ES Bulk失敗、ディスク使用量を確認する。
- `batch/run_batch.sh` は現在S3バックアップも含む。初回移行の代わりに全体を先に起動しない。
- 対象SHA、APIの反映先、Piで実行した手順、件数、未判定IDと再試行予定、画面確認結果を記録する。

## 切り戻し

最初に定期バッチを再び止める。旧コードのライブ専用処理へ新しい共通NDJSONを渡してはいけない。

- **投入前**: 旧コード／旧batchイメージと保全した旧NDJSONへ戻せる。変更後APIは旧データと互換性がある。
- **投入後**: 原則として、絞り込み済みAPIと追加フィールドは維持し、バッチを止めて修正する。追加mappingは削除しない。単純に旧APIへ戻すと新規通常投稿が配信一覧に出る。
- **完全なデータ復元が必要**: 事前snapshot等から別インデックスへ復元し、内容確認後に利用側の参照先を切り替える。既存本番インデックスの削除・上書き復元は個別に判断する。バックフィル以降の新しい処理ステータス等も巻き戻るため、自動で実施しない。

## PiのCodexに渡す指示

以下をコピーし、対象SHAを埋めて依頼する。API先行反映は実際に完了した後でその旨を伝える。

```text
utsulogのIssue #1・#2の本番反映を行ってください。
対象リリースSHA: <完全なSHA>

まず現在のリポジトリ、定期バッチの起動方法、Compose/env指定、マウント、
本番ESの接続先・mapping・コメント用kuromoji、復旧手段を読み取り確認してください。
認証情報やenvの値は出力しないでください。
未コミット変更を破棄せず、他のジョブを停止しないでください。

対象リリースの docs/operations/video-flags-production-rollout.md を取得して読み、
このPiの実構成に合わせたコマンドを用意してください。
APIの先行反映が完了しているか確認し、未完了ならデータ投入に進まないでください。

定期バッチの停止・保全、コード更新・batchビルド、2動画の別NDJSON収集と検査、
本番への部分投入、対象通常投稿のコメント取得・投入、全件バックフィル、
結果確認、定期実行再開までを実施してください。
各段階の確認が通らなければ後続へ進まず、原因と復旧案を示してください。
本番インデックスを削除・再作成しないでください。

get_comments/import_commentsは終了コードだけでなくログとES件数も確認してください。
スタンプ画面を操作できない場合は確認不能を明示し、利用者による確認項目を残してください。
最後に実行SHA、変更前後の件数、対象2動画の値、コメント投入結果、
スケジュール再開状況、未判定の再試行予定を報告してください。
```
