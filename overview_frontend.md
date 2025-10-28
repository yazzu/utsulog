## 概要
youtube の chat log を 全文検索して、 チャットのタイムスタンプに合ったリンクを生成するWebアプリケーション

### Platform
- Elastic Search
    - Elastic Cloud
- Web Application Server
    - AWS Fargate
- Static Hosting(Html,Js,image,chatlog)
    - AWS S3

### Overview
- フロントエンド
    - ユーザーが検索ボックスに入力する。
    - 入力が0.3秒停止したら [Debounce]、入力内容をAPIサーバーに送信する。

- APIサーバー (Python (FastAPI/Flask))
    - フロントエンドから検索クエリを受け取る。
    - そのクエリを使って Elasticsearch に検索をリクエストする。

- 検索エンジン (Elasticsearch)
    - N-gramインデックスを使って高速に検索を実行し、ヒットしたデータ（上記JSON）をAPIサーバーに返す。

- フロントエンド (vite + React + TypeScript)
    - APIサーバーから検索結果（JSONの配列）を受け取る。
    - 結果をループ処理し、タイムスタンプ付きのリンク（例: https://www.youtube.com/watch?v={video_id}&t={timestamp_sec}s）として画面に描画する。

### Layout
- test/draft.html に Sample Layout がある

#### 画面構成
- 検索ボックス
    - テキストボックス
    - カスタムEmoji 用の パレット

- 検索結果
    - チャットメッセージ
    - タイムスタンプ
    - 投稿者名
    - マウスオーバーのポップアップ
        - タイムスタンプ時点 の サムネイル
        - タイムスタンプ時点 の 動画URL
- フィルター
    - 動画投稿日 From
    - 動画投稿日 To
    - 投稿者名
