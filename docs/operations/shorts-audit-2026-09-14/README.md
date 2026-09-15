# Issue #4: Shorts除外の事前調査

2026-09-14 22:09 JST に公開Shortsタブと既存データを読み取り照合した。ES・共通NDJSONへの変更は行っていない。

## 結果

| 対象 | 件数 |
| --- | ---: |
| 公開Shortsタブ | 534 |
| videos_v3全件 | 1,364 |
| ES内のShorts除外候補 | 533 |
| 共通NDJSON全件 | 1,364 |
| 共通NDJSON内のShorts除外候補 | 533 |
| 候補のみ削除した場合のES残数（取得時点） | 831 |

候補は [candidates.csv](candidates.csv)、取得時点の集計は [summary.json](summary.json) を参照。
533件すべて `isLive=false`・`membersOnly=false`。通常投稿の対照動画 `qsOw7Q8WJQA` はESに存在し、Shorts一覧には含まれない。
公開Shorts `nmjy9oEihiM` はES未登録だった。既存削除だけでなく新規投入防止が必要。

## 判定方法と限界

yt-dlp 2026.08.19で次の読み取りを行い、全ページ取得が正常終了したJSONの `entries` を使用した。動画本体は取得しない。

```sh
python3 /tmp/utsulog-yt-dlp --flat-playlist --skip-download \
  --dump-single-json --sleep-requests 2 --retries 1 --extractor-retries 1 \
  https://www.youtube.com/channel/UC64MV1Dfq3prs9CccXg09rQ/shorts \
  > /tmp/utsulog-shorts.json
```

チャンネルIDと各エントリの `/shorts/{id}` URLの一致を確認した。ESは全件検索の `track_total_hits`、返却件数の一致、タイムアウトなし、シャード失敗なしを確認してIDで照合した。共通NDJSONは `/home/yazzu709/share/utsulog-data/videos/videos.ndjson` を読み取り確認した。

Shortsタブに掲載されたことを肯定の根拠とする。未掲載は非Shortsの証明ではなく、非公開・会員限定・未掲載のShortsを網羅したとはいえない。候補533件は動画ごとのページを再確認した数ではない。HTML/API変更や取得失敗を空一覧として扱わないことが必要。

公式Data APIのVideoリソースには直接のShorts判定フィールドがない。尺のみ・タイトルの `#shorts` のみで削除しない。

- [YouTube Data API: Videos](https://developers.google.com/youtube/v3/docs/videos)
- [YouTube: 3分間のShortsの分類条件](https://support.google.com/youtube/answer/15424877?hl=ja)
- [yt-dlp: 特定タブの取得](https://github.com/yt-dlp/yt-dlp#readme)

## 推奨する実装・反映順序

1. Shortsタブから判定済みIDと根拠・取得日時を保存する仕組みを追加する。未掲載をfalseにせず、既知IDは一覧から消えても自動解除しない。解除は再確認を伴う明示的な処理とする。
2. `get_videos.py` でアップロード一覧・過去NDJSON・`--include-index` のIDを統合した後に除外する。会員判定前に除外すれば不要な個別アクセスも減る。
3. `import_videos.py` にも同じ判定済みIDによる投入防止を設ける。過去NDJSON・明示ID収集からの復活を防ぐ。取得失敗時は不完全な候補一覧や共通NDJSONを公開せず中断する。
4. 判定、一覧取得失敗、ページ継続、通常投稿保持、再投入・バックフィルでの復活防止をテストする。
5. 定期バッチとの競合を避けて除外処理を反映し、最新データで候補を再生成する。削除前の対象 `_source` を退避し、明示した候補IDのみを削除する。`python batch/prune_shorts.py candidates.txt` で dry-run確認し、レビュー後だけ `--execute` を付ける。インデックス再作成は不要。
6. 共通NDJSONからも除外し、両アプリの表示・集計を確認する。既存コメントインデックスの削除は今回の候補一覧に含めず、スタンプ側が動画ID不在のコメントを集計するかを別途確認する。

定期実行では `batch/run_batch.sh` が `get_videos.py` の後にShorts manifestを必須検証する。manifestがない、対象チャンネルと一致しない、空または壊れている場合は `set -e` によりチャット取得やES投入へ進まない。

実装・本番削除は未実施。CSVは時点付きのレビュー用候補であり、そのまま将来の削除入力に使わず再照合する。
