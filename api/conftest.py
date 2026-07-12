import os

os.environ.setdefault("ELASTICSEARCH_HOST", "http://localhost:9200")
os.environ.setdefault("ELASTICSEARCH_API_KEY", "dummy-key")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("VIDEOS_INDEX_NAME", "videos")
os.environ.setdefault("CHAT_LOGS_INDEX_NAME", "chat_logs")
os.environ.setdefault("THUMBNAIL_BASE_URL", "http://localhost/thumbnails")
os.environ.setdefault("AUTHOR_ICON_BASE_URL", "http://localhost/author-icons")
os.environ.setdefault("SEARCH_TOTAL_HITS", "true")
