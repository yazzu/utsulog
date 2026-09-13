# ショート動画の除外機能（設計メモ）

## 背景

`batch/get_videos.py` はコミット `e340dde971a12f91f15662147bcf8975ab0578d4`（Issue #12、`75beb45`）でライブ配信以外の動画（通常投稿）も収集するようになった。この変更に伴い、YouTube Shorts（ショート動画）も収集対象に含まれるようになった。ショート動画を一覧・検索から除外したいという要望がある。

本ドキュメントは実装前の設計検討の記録。**未実装・未反映**。別の本番リリース対応と並行しているため、実装は別途行う。

## 判定方法の検討と結論

### 候補1: duration（動画の長さ）による判定 — 不採用

`videos().list` に `contentDetails` パートを追加すれば `duration`（ISO8601）を取得できる。追加のAPIクォータ消費なし、動画ごとの追加HTTPリクエストも不要という利点がある。

しかし `contentDetails` には縦横比・幅・高さの情報が含まれない。そのため「60秒以下」のようなduration閾値だけで判定すると、以下のような**横型の動画を誤ってショート扱いしてしまう（false positive）**：

- 横型の切り抜き動画（1分未満のもの）
- 短いOP動画（1分未満のもの）

これらはYouTube上では実際にはショートとして扱われない（`/shorts/` 棚に出てこない）動画であり、除外したくないものまで除外してしまうリスクがあるため不採用とした。

### 候補2: shorts URL / oEmbed による判定 — 採用

`batch/video_membership.py` の `get_membership()` と同様のパターンで、動画ごとにHTTPリクエストを行い、YouTube自身のショート判定結果を利用する。具体的には `https://www.youtube.com/shorts/{video_id}` へのアクセス結果（ショートでなければ `/watch?v=` にリダイレクトされる）、または `https://www.youtube.com/oembed?url=.../shorts/{id}&format=json` のステータスコード（200=ショート、404=非ショート）を根拠にする。

YouTube自身の分類（アスペクト比・投稿方法等を加味した判定）をそのまま使えるため、duration閾値による誤判定が起きない。トレードオフは動画ごとに追加のHTTPリクエストが1本発生すること（`membersOnly` 判定と合わせて動画1件あたり最大2本のリクエストになり、収集処理は遅くなる）。

## フィールド契約（`isShort`）

`membersOnly` と同じ `(verdict, evidence)` 形式の判定関数として実装し、`video_membership.py` に倣う。ただし**再チェックの方針は `membersOnly` と異なる**：

- `membersOnly` は動画の公開範囲が後から変わりうる（会員限定⇄一般公開）ため、収集のたびに毎回問い合わせて最新化する。
- `isShort` は動画の尺・投稿枠がアップロード後に変わらない固定属性であるため、**一度 `true`/`false` に確定した動画は再問い合わせしない**。`load_previous()` で読み込んだ前回値をそのまま引き継ぐ。
- 前回値が `null`（未判定・通信失敗等）の動画のみ、今回改めて問い合わせる。

値の意味:

- `true`: shorts URL / oEmbed 経由でショートと確認できた場合。
- `false`: 同様に非ショートと確認できた場合。
- `null`（NDJSON上はフィールド欠落）: 通信失敗・想定外レスポンス等で未判定。`membersOnly` と同様、Elasticsearch投入時にnullフラグは取り除き、既存の確定値を保持する。

## 実装対象（想定）

- `batch/video_membership.py` 相当のモジュール、または同ファイル内に `is_short(video_id)` のような判定関数を追加（`(verdict, evidence)` を返す）。
- `batch/get_videos.py`:
  - `collect()` 内で `previous` から `isShort` を引き継ぐ対象フィールドに追加。
  - `isShort` が前回値として確定していない動画のみ新規判定を実行。
- `batch/import_videos.py`:
  - `create_index_if_not_exists()` の `properties` に `'isShort': {'type': 'boolean'}` を追加。
  - `generate_bulk_payload_from_chunk()` のnull/boolean検証対象フィールド（`membersOnly`, `isLive`）に `isShort` を追加。
- `api/main.py` の `/videos` エンドポイント:
  - 既存の `isLive`/`actualEndTime` によるbool queryフィルタと同じ場所に、`isShort` を除外する条件（例: `{"term": {"isShort": False}}` 相当、または `isShort` フィールド欠落＝未判定分の扱いを別途検討）を追加。
  - 収集段階ではデータを落とさず、表示（API）側で絞り込む方針。直近のIssue #12対応（収集段階でデータを落とさず表示側で判断する方針への修正）と整合させるため。
- 必要であれば `batch/video_policy.py` に `is_short(video)` のような小さな純粋関数を追加し、`dl_video.py` 等の他バッチからも再利用できるようにする（`is_completed_live()` と同じパターン）。

## 未実施事項

- 具体的な判定関数の実装・テスト（`batch/tests/` への追加）。
- ES `videos_v3` インデックスへのmapping追加・バックフィル。
- `api/main.py` のフィルタ条件の具体的なクエリ実装と検証。
- 本番反映（他の本番リリース対応完了後に着手）。
