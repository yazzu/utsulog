cp -p /mnt/miniutsuro/utsulog-data/videos/videos.ndjson /mnt/f/Dev/utsulog/videos/videos.ndjson
docker compose run --rm --no-deps batch python batch/vtt_to_csv.py
docker compose --env-file .env.local run --rm --no-deps batch python batch/import_chatlogs.py
