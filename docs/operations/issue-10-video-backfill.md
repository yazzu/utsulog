# Issue #10 欠落動画のバックフィル

## 確認結果（2026-09-21）

対象の6動画は、既存の `videos_v3`、永続 `videos.ndjson`、匿名で取得する
チャンネルの uploads 再生リストのいずれにも存在しなかった。

`get_videos.py --include-index` の入力は uploads・既存NDJSON・既存インデックスの
和集合である。このため、3経路すべてから欠落したIDは自動では発見できない。
最初の1回だけIDを明示して投入する必要がある。投入後はインデックスから再取得対象へ
戻るため、通常バッチの `--include-index` で継続的に再判定される。

一時ファイルへの試験収集では、6件すべてについて次を確認した。

- `videoDetailsStatus=ok`
- `isLive=true`
- `actualStartTime` と `actualEndTime` を取得可能
- `membersOnly=true`
- `membersOnlyEvidence=watch_player_members_only`

確認時点の既存データは、インデックス838件、NDJSON 838件、差分0件だった。
既存838件は通常の `--include-index` による全件バックフィルの対象になる。

## 実行手順

定期バッチと同時実行しない。接続先が本番 `videos_v3` であることを確認し、
共通NDJSONを直接置き換えない一時ファイルで先行収集する。

```bash
issue10_ndjson=/app/videos/issue-10-backfill.ndjson

docker compose run --rm --no-deps \
  -e VIDEOS_NDJSON="$issue10_ndjson" batch \
  python batch/get_videos.py \
    --video-id 4XHsKDflKjk \
    --video-id eLERQp4e3MY \
    --video-id Wz2CDytB4Ao \
    --video-id F2YXssqgn5Q \
    --video-id C6wL1oAv_g4 \
    --video-id 9oWgSDD0FHU
```

6行あること、ID重複がないこと、上記フィールドが取得できていることを検査してから、
同じ一時ファイルを部分投入する。

```bash
docker compose run --rm --no-deps \
  -e VIDEOS_NDJSON="$issue10_ndjson" batch \
  python batch/import_videos.py
```

`import_videos.py` は動画IDを `_id` にした `update` + `doc_as_upsert` を使うため、
既存インデックスを削除・再作成しない。投入後、6件の `_source` とインデックス件数を
確認する。期待件数は、同時期の別の追加・削除がなければ838件から844件になる。

最後に共通NDJSONを再生成・投入する。ここで新規6件はインデックス側から入力へ戻る。

```bash
docker compose run --rm --no-deps batch \
  python batch/get_videos.py --include-index
docker compose run --rm --no-deps batch \
  python batch/import_videos.py
```

全件投入後は、6件が共通NDJSONと `videos_v3` の両方に存在すること、既存動画が
失われていないこと、`thumbnail_created` などの既存処理フィールドが維持されている
ことを確認する。APIの `/videos` は終了済みライブのみを返すため、今回の6件は
終了日時が取得できていれば検索用動画一覧の条件を満たす。ただし別アプリ側では
`membersOnly=true` を使って除外できる。

## 本番部分投入結果（2026-09-21）

上記の専用NDJSONを使って `videos_v3` へ6件を部分投入した。refresh後の件数は
838件から844件になった。対象6件はすべて保存済みで、`isLive=true`、開始・終了日時、
`membersOnly=true`、`membersOnlyEvidence=watch_player_members_only`、
`videoDetailsStatus=ok` を確認した。

共通NDJSONの全件再生成はこの部分投入では実行していない。対象IDはインデックスへ
入ったため、次回の通常バッチが実行する `get_videos.py --include-index` で共通NDJSONへ
取り込まれ、以降も再判定される。
