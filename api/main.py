import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from elasticsearch import Elasticsearch
from typing import List, Dict, Any

# 環境変数からElasticsearchのホストを取得
ELASTICSEARCH_HOST = os.getenv("ELASTICSEARCH_HOST", "http://elasticsearch:9200")

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    """
    アプリケーション起動時にElasticsearchへの接続を確立する。
    """
    try:
        es = Elasticsearch(ELASTICSEARCH_HOST)
        if es.ping():
            print("Successfully connected to Elasticsearch.")
            app.state.es = es
        else:
            print("Failed to connect to Elasticsearch: ping failed.")
            app.state.es = None
    except Exception as e:
        print(f"Error connecting to Elasticsearch during startup: {e}")
        app.state.es = None

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

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

# (...中略...)

@app.get("/search")
def search_chat_logs(
    q: str = "", 
    from_: int = 0, 
    exact: bool = False, 
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    request: Request = None
):
    """
    Elasticsearchを使用してチャットログを検索するエンドポイント。
    ページネーション、完全一致検索、日付範囲フィルターをサポート。
    """
    es = request.app.state.es
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch service is unavailable.")

    if not q:
        return {"total": 0, "results": []}

    # キーワード検索のクエリ部分
    if exact:
        must_query = {
            "match_phrase": {
                "message": q
            }
        }
    else:
        must_query = {
            "multi_match": {
                "query": q,
                "fields": ["message", "author"]
            }
        }

    # 日付範囲フィルターの部分 (timestampフィールドを使用)
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

    # Elasticsearchの検索クエリ全体を構築
    search_query = {
        "from": from_,
        "query": {
            "bool": {
                "must": must_query,
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
        response = es.search(index="youtube-chat-logs", body=search_query)
        
        # 総ヒット件数を取得
        total_hits = response["hits"]["total"]["value"]
        
        # フロントエンド向けの形式にレスポンスを整形
        results = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
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
            }
            results.append(result)
            
        return {"total": total_hits, "results": results}

    except Exception as e:
        print(f"検索中にエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="検索処理中にエラーが発生しました。")