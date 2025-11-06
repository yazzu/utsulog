import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from elasticsearch import Elasticsearch
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

# 環境変数からElasticsearchのホストを取得
ELASTICSEARCH_HOST = os.getenv("ELASTICSEARCH_HOST", "http://elasticsearch:9200")
THUMBNAIL_BASE_URL = os.getenv("THUMBNAIL_BASE_URL", "http://localhost:8000/thumbnails")

app = FastAPI()
# Elasticsearchに接続
es = Elasticsearch(ELASTICSEARCH_HOST)

# 静的ファイル（サムネイル画像）を配信するためのマウント
app.mount("/thumbnails", StaticFiles(directory="/thumbnails"), name="thumbnails")

def calculate_thumbnail_url(video_id: str, elapsed_time: str) -> str:
    """
    videoIdとelapsedTimeからサムネイル画像のURLを生成する。
    elapsedTimeは3分ごとに切り捨てられる。
    """
    if not video_id or not elapsed_time:
        return ""

    try:
        parts = list(map(int, elapsed_time.split(':')))
        seconds = 0
        if len(parts) == 3:
            seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            seconds = parts[0] * 60 + parts[1]
        elif len(parts) == 1:
            seconds = parts[0]

        # 3分（180秒）単位で切り捨て
        rounded_seconds = (seconds // 180) * 180
        
        m, s = divmod(rounded_seconds, 60)
        h, m = divmod(m, 60)
        
        timestamp_str = f"{h:02d}{m:02d}{s:02d}"
        filename = f"{video_id}_{timestamp_str}.jpg"
        
        # APIサーバーのURLをベースにサムネイルURLを構築
        return f"{THUMBNAIL_BASE_URL}/{filename}"

    except (ValueError, IndexError):
        return ""

@app.on_event("startup")
async def startup_event():
    app.state.es = es

# CORSミドルウェアの設定
origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Utsulog API"}

@app.get("/videos")
def get_videos(request: Request):
    """
    Elasticsearchから動画のリストを取得するエンドポイント。
    video_urlからvideoIdを抽出し、重複を除外する。
    """
    es = request.app.state.es
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch service is unavailable.")

    search_query = {
        "query": {
            "match_all": {}
        },
        "sort": [
            {
                "publishedAt.keyword": {
                    "order": "desc"
                }
            }
        ],
        "size": 1000 # 取得する動画の最大数
    }

    try:
        response = es.search(
            index="videos", 
            query=search_query["query"],
            sort=search_query["sort"],
            size=search_query["size"]
        )
        
        videos = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            video_url = source.get("video_url")
            if not video_url:
                continue
            
            try:
                parsed_url = urlparse(video_url)
                # YouTubeのURLから 'v' パラメータを抽出
                video_id = parse_qs(parsed_url.query).get('v', [None])[0]
                if not video_id:
                    continue
            except (KeyError, IndexError):
                continue

            video = {
                "videoId": video_id,
                "title": source.get("title"),
                "thumbnail_url": source.get("thumbnail_url"),
                "publishedAt": source.get("publishedAt"),
            }
            videos.append(video)
            
        return {"videos": videos}

    except Exception as e:
        print(f"動画リストの取得中にエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="動画リストの取得中にエラーが発生しました。")

@app.get("/search")
def search_chat_logs(
    q: str = "", 
    from_: int = 0, 
    exact: bool = False, 
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    author_name: Optional[str] = None,
    video_id: Optional[str] = None,
    request: Request = None
):
    """
    Elasticsearchを使用してチャットログを検索するエンドポイント。
    ページネーション、完全一致検索、日付範囲フィルター、動画IDフィルターをサポート。
    """
    es = request.app.state.es
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch service is unavailable.")

    must_clauses = []
    # キーワード検索のクエリ部分
    if q:
        if exact:
            must_clauses.append({
                "match_phrase": {
                    "message": q
                }
            })
        else:
            must_clauses.append({
                "multi_match": {
                    "query": q,
                    "fields": ["message", "author"]
                }
            })

    # フィルターの部分
    filters = []
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            ts_from = int(dt_from.timestamp() * 1000)
            filters.append({"range": {"timestamp": {"gte": ts_from}}})
        except ValueError:
            pass # 不正な日付形式は無視
    if date_to:
        try:
            # 指定日の終わりまで含めるため、次の日の0時より小さい範囲を指定
            dt_to = datetime.fromisoformat(date_to) + timedelta(days=1)
            ts_to = int(dt_to.timestamp() * 1000)
            filters.append({"range": {"timestamp": {"lt": ts_to}}})
        except ValueError:
            pass # 不正な日付形式は無視

    if author_name:
        filters.append({"term": {"authorName.keyword": author_name}})

    if video_id:
        filters.append({"term": {"videoId.keyword": video_id}})

    # Elasticsearchの検索クエリ全体を構築
    search_query = {
        "from": from_,
        "query": {
            "bool": {
                "must": must_clauses,
                "filter": filters
            }
        },
        "sort": [
            {
                "datetime.keyword": {
                    "order": "desc"
                }
            }
        ],
        "size": 100 # 1回あたりの取得件数
    }

    try:
        response = es.search(
            index="youtube-chat-logs",
            from_=search_query["from"],
            query=search_query["query"],
            sort=search_query["sort"],
            size=search_query["size"]
        )
        
        # 総ヒット件数を取得
        total_hits = response["hits"]["total"]["value"]
        
        # フロントエンド向けの形式にレスポンスを整形
        results = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            
            thumbnail_url = calculate_thumbnail_url(source.get("videoId"), source.get("elapsedTime"))

            result = {
                "id": hit["_id"],
                "videoId": source.get("videoId"),
                "videoTitle": source.get("videoTitle"),
                "datetime": source.get("datetime"),
                "elapsedTime": source.get("elapsedTime"),
                "timestampSec": source.get("timestamp"),
                "message": source.get("message"),
                "author": source.get("authorName"),
                "authorChannelId": source.get("authorChannelId"),
                "thumbnailUrl": thumbnail_url,
            }
            results.append(result)
            
        return {"total": total_hits, "results": results}

    except Exception as e:
        print(f"検索中にエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="検索処理中にエラーが発生しました。")
