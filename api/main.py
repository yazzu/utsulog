from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any

app = FastAPI()

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
def search_chat_logs(q: str = ""):
    """
    チャットログを検索するエンドポイント。
    現時点ではダミーデータを返します。
    """
    if not q:
        return []

    # フロントエンドで使うためのダミーデータ
    dummy_data = [
        {
            "id": "1",
            "video_id": "sample_video_A",
            "timestamp_sec": 5025,
            "author": "サンプルユーザー1",
            "message": f"「{q}」の検索結果メッセージ1。お疲れ様でした！",
            "video_title": "サンプル動画A",
            "thumbnail_url": "https://placehold.co/400x225/334155/e2e8f0?text=Thumbnail [1:23:45]"
        },
        {
            "id": "2",
            "video_id": "sample_video_B",
            "timestamp_sec": 920,
            "author": "長めの名前のユーザーさん",
            "message": f"この瞬間の「{q}」が一番好き 😂",
            "video_title": "サンプル動画B",
            "thumbnail_url": "https://placehold.co/400x225/1e293b/e2e8f0?text=Thumbnail [0:15:20]"
        },
        {
            "id": "3",
            "video_id": "sample_video_A",
            "timestamp_sec": 11111,
            "author": "サンプルユーザー3",
            "message": f"長時間配信お疲れ様でした！「{q}」も最高でした！",
            "video_title": "サンプル動画A",
            "thumbnail_url": "https://placehold.co/400x225/4b5563/e2e8f0?text=Thumbnail [3:05:11]"
        }
    ]
    
    return dummy_data