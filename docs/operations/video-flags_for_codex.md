# Issue #6 本番バックフィル実行手順（Raspberry Pi Codex向け）

以下のプロンプトをRaspberry Pi環境のCodexに渡す。実行前に `<承認済みSHA>` を、レビュー・マージ済みのリリースコミットSHAへ置き換えること。

```text
utsulog Issue #6 の本番バックフィルを実施してください。

目的:
- 動画 ykmsXIUyAnE を本番 Elasticsearch の videos_v3 に
  membersOnly=true として安全に部分更新する
- その後、全動画のバックフィルを行う
- 次回定期実行でも対象動画が維持される構成を確認する

承認済みリリースコミット:
<承認済みSHA>

重要な制約:
- 本番インデックスを削除・再作成しない
- git reset --hard や既存の未コミット変更の破棄をしない
- 認証情報、APIキー、パスワード、トークンを出力しない
- 本番で現在使われているComposeファイル、envファイル、project名を確認し、既存運用と同じ指定を使う
- .env.prod を使っていると推測せず、実際の定期実行設定から確認する
- 対象のcron/systemd timerだけを一時停止する。他のジョブは変更しない
- 実行中のbatchがあれば強制終了せず、正常終了を待つ
- API取得失敗、429、判定不能、期待値不一致、ES Bulkエラーがあれば投入せず停止して報告する
- 一時確認NDJSONには既存の共通 videos.ndjson と異なる名前を使う
- 作業中は進捗を随時報告する

手順:

1. リポジトリと本番実行経路を調査する
- リポジトリの絶対パス
- 現在のブランチ、HEAD SHA、git status
- cron、systemd timer等の定期実行経路と実行ユーザー
- 実際に使用しているdocker composeの -f、--env-file、-p 等
- 実行中のbatchコンテナ
- batchから見たVIDEOS_NDJSONの永続マウント
- Elasticsearch接続先が本番であること
- VIDEOS_INDEX_NAMEがvideos_v3であること
- ESのsnapshot等、既存の復旧手段と最終成功時刻

秘密値そのものは表示しないこと。

2. 未コミット変更がある場合
- 内容を確認し、今回の更新と衝突しないか報告する
- reset、checkout、stashを勝手に実行しない
- 安全にfast-forward更新できない場合は作業を止めて報告する

3. 対象の定期ジョブを一時停止する
- 実行中のbatchがあれば正常終了を待つ
- 停止前の設定と状態を記録し、後で同じ状態へ戻せるようにする

4. コードを更新する
- git fetch origin
- 承認済みSHAがorigin上に存在することを確認する
- 通常の本番ブランチ運用に従いgit pull --ff-onlyする
- 更新後のHEADが承認済みSHAと一致することを確認する
- 一致しなければビルドやデータ更新へ進まない
- 既存の本番Compose指定を使ってbatchイメージをビルドする

5. 更新前の本番データを読み取り確認する
- videos_v3のmappingと総件数
- _id=ykmsXIUyAnE の存在有無と_source
- membersOnly、membersOnlyEvidence、membersOnlyCheckedAt
- actualStartTime、actualEndTime、isLive
- thumbnail_created等の既存処理フィールド
- 値を記録するが、秘密情報は出力しない

6. 対象動画だけを別NDJSONへ収集する
- /app/videos/issue6-UTC時刻.ndjson のような一意な名前を使う
- VIDEOS_NDJSONをその一時ファイルへ差し替えた一時コンテナで実行する
- 実行コマンド:
  python batch/get_videos.py --video-id ykmsXIUyAnE

7. 投入前検査
一時NDJSONが1行だけで、以下を満たすことをプログラムで検証する:
- video_urlのIDがykmsXIUyAnE
- membersOnly is True
- membersOnlyEvidence == "watch_player_members_only"
- videoDetailsStatus == "ok"
- isLive is True
- actualStartTimeが存在する
- actualEndTimeが存在する

失敗したらESへ投入せず、取得ログと安全に表示できるフィールドだけを報告する。

8. 対象1件を本番ESへ投入する
- 同じ一時NDJSONをVIDEOS_NDJSONに指定して
  python batch/import_videos.py
  を実行する
- これは既存_idへのupdate + doc_as_upsertであることを確認する
- インデックス削除、再作成、全置換をしない

9. 対象1件の投入後確認
本番videos_v3の_id=ykmsXIUyAnEを読み直し、以下を確認する:
- membersOnly is True
- membersOnlyEvidence == "watch_player_members_only"
- membersOnlyCheckedAtが更新されている
- isLive is True
- actualEndTimeが存在する
- thumbnail_created等、投入前に存在した今回対象外のフィールドが維持されている
- インデックス総件数が不自然に減っていない

10. 全件バックフィル
対象1件が正常な場合のみ実施する:
- 通常の共通VIDEOS_NDJSONを使う
- python batch/get_videos.py --include-index
- 完了まで待つ。短時間で再実行しない
- Membership summary、429、HTTPエラー、unknown、失敗率、中断有無を確認する
- 収集が異常終了した場合、import_videos.pyは実行しない
- NDJSON件数、動画ID重複、membersOnlyのtrue/false/null件数、
  membersOnlyEvidence別件数、videoDetailsStatus=unavailable件数を確認する
- 全件unknownなど不自然な結果なら投入せず停止する
- 正常なら python batch/import_videos.py を実行する
- Bulk部分エラーも成功扱いにしない

11. 全件投入後確認
- videos_v3の総件数が不自然に減っていない
- ykmsXIUyAnEがmembersOnly=trueのまま
- 未判定レコードによって既存の確定済みmembersOnlyが消えていない
- thumbnail_created等の既存処理フィールドが維持されている
- mapping上のmembersOnlyとisLiveがboolean
- 定期実行スクリプトが get_videos.py --include-index を使用している

12. アプリ確認
可能ならutsulog-stampの本番プレイリスト/APIを確認し、
ykmsXIUyAnEが表示されないことを確認する。
アクセス方法が不明なら推測で変更せず、その確認だけ未実施として報告する。

13. 定期実行を元の状態に戻す
- 成功時は停止した対象スケジュールだけを元の状態へ戻す
- 再開設定が停止前と同じことを確認する
- 他のcron/timerを変更しない

14. 最終報告
以下を秘密情報なしで報告する:
- 実行ホスト、リポジトリパス、反映SHA
- 使用したCompose指定の種類
- 停止・再開した定期ジョブ
- 対象動画の投入前後の安全なフィールド
- 全件収集数
- membersOnly true/false/null件数
- unknown/HTTP失敗/429件数
- ES投入結果と総件数の前後
- 既存処理フィールド維持の確認結果
- utsulog-stampでの確認結果
- 残課題
```

全件バックフィルは最低でも約45分かかる。Codexには途中で終了させず、収集完了とElasticsearch投入後の検証まで継続させること。
