# YouTubeコメント用Elasticsearchインデックス設計

## 位置づけ

このドキュメントは **スキーマ定義のみ** を目的とする。取得バッチ・投入処理の実装は本プロジェクト(utsulog-stamp)のスコープ外であり、`utsulog`プロジェクト側で別途構築される想定。utsulog-stampはこのインデックスが将来投入された際に、`youtube-chat-logs_v3`と同様の方法で読み取り、チャットと合わせて「コメント済み」スタンプ判定に利用する。

## インデックス名

`youtube-comments_v1`

既存の`youtube-chat-logs_v3`は複数回のスキーマ改版を経て`_v3`まで進んでいる経緯があるため、コメント用は独立採番とし`_v1`から開始する。

## フィールド設計

`youtube-chat-logs_v3`と同じフィールド命名規約(`videoId`, `videoTitle`, `authorName`, `authorChannelId`, `datetime`, `timestamp`, `type`)に揃えることで、将来チャット・コメントを横断してスタンプ判定クエリを組めるようにする。

```json
{
  "id": "UgxAbCdEfGhIjKlMnOp1234AaBbCc",
  "videoId": "06KIXbb1c0s",
  "videoTitle": "【#スーパーマリオブラザーズ2】今再びの8面【＃レトロゲーム】",
  "type": "comment",
  "message": "今日も配信お疲れ様でした！",
  "authorName": "みひろ",
  "authorChannelId": "UCTvE5zKEhbmA1Lqb972sHEA",
  "publishedAt": "2025-07-06T21:15:32Z",
  "datetime": "2025-07-07 06:15:32",
  "timestamp": 1751829332000,
  "likeCount": 3,
  "isReply": false,
  "parentId": null
}
```

### フィールド説明

| フィールド | 型 | 説明 |
|---|---|---|
| `id` | keyword | YouTubeコメントID。返信コメントも含め、YouTube Data APIが返すグローバルに一意なコメントIDをそのまま使用する。 |
| `videoId` | keyword | コメント対象の動画ID。`youtube-chat-logs_v3`と同じ値域。 |
| `videoTitle` | text/keyword | 動画タイトル(非正規化。検索・表示の簡略化のため)。 |
| `type` | keyword | 固定値 `"comment"`。チャット(`"chat"`)・字幕(`"transcript"`)と区別するための識別子。 |
| `message` | text | コメント本文(`commentThreads.list`の`textDisplay`または`textOriginal`)。 |
| `authorName` | keyword | 投稿者の表示名(取得時点のスナップショット)。 |
| `authorChannelId` | keyword | 投稿者のチャンネルID。スタンプ判定はこのフィールドで名寄せする。 |
| `publishedAt` | date (ISO8601) | コメントの投稿日時(UTC)。YouTube APIの`publishedAt`をそのまま保持。 |
| `datetime` | keyword | JST(`Asia/Tokyo`)に変換した`YYYY-MM-DD HH:MM:SS`文字列。`youtube-chat-logs_v3`と同じ表示用フォーマット規約。 |
| `timestamp` | long (epochミリ秒) | ソート・範囲検索用。`youtube-chat-logs_v3`の`timestamp`と同じ単位。 |
| `likeCount` | integer | コメントのいいね数(参考情報。スタンプ判定には使用しない)。 |
| `isReply` | boolean | 返信コメントかどうか。 |
| `parentId` | keyword or null | 返信の場合は親コメントのID。トップレベルコメントは`null`。 |

## 意図的に含めないフィールド

- `elapsedTime`(配信経過時間): コメントはYouTube API上、配信のタイムライン位置(再生時間)と紐付く情報を持たないため対象外。チャットログのようなタイムスタンプ付きサムネイル連携は行わない。

## utsulog-stamp側での利用方法(将来)

`GET /stamps`のスタンプ判定ロジックに、`youtube-chat-logs_v3`の`authorChannelId`集計と同様に`youtube-comments_v1`への`authorChannelId.keyword`集計を追加し、両方の集合の和集合を「チャット済みまたはコメント済み」の判定に用いる。インデックスが存在しない間はチャット集計のみで動作する(クエリ失敗時のフォールバックではなく、インデックス有無を設定/フィーチャーフラグで切り替える)。
