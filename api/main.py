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

@app.get("/search")
def search_chat_logs(q: str = "", request: Request = None):
    """
    Elasticsearchを使用してチャットログを検索するエンドポイント。
    """
    es = request.app.state.es
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch service is unavailable.")

    if not q:
        return []

    # Elasticsearchの検索クエリ
    search_query = {
        "query": {
            "multi_match": {
                "query": q,
                "fields": ["message", "author"]
            }
        },
        "size": 100 # 最大100件まで取得
    }

    try:
        response = es.search(index="youtube-chat-logs", body=search_query)
        
        # フロントエンド向けの形式にレスポンスを整形
        results = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            result = {
                "id": hit["_id"],
                "video_id": source.get("video_id"),
                "timestamp_sec": source.get("timestamp_sec"),
                "author": source.get("author"),
                "message": source.get("message"),
                "video_title": source.get("video_title"),
                "thumbnail_url": source.get("thumbnail_url")
            }
            results.append(result)
            
        return results

    except Exception as e:
        print(f"検索中にエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail="検索処理中にエラーが発生しました。")