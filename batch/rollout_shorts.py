"""One-time, reviewed Shorts removal. Dry-run unless --execute is supplied."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from get_videos import write_to_ndjson
from shorts import load_manifest


def video_id(row):
    return parse_qs(urlparse(row['video_url']).query)['v'][0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    channel_id = os.environ['CHANNEL_ID']
    ids = load_manifest(channel_id=channel_id, required=True)
    source_path = Path(os.environ['VIDEOS_NDJSON'])
    rows = [json.loads(line) for line in source_path.read_text().splitlines() if line.strip()]
    retained = [row for row in rows if video_id(row) not in ids]
    source_ids = {video_id(row) for row in rows}
    es_url = os.environ['ELASTICSEARCH_URL'].rstrip('/')
    index = os.environ['VIDEOS_INDEX_NAME']
    auth = (os.environ['ELASTICSEARCH_ADMIN'], os.environ['ELASTICSEARCH_PASSWORD'])
    verify = os.environ['ELASTICSEARCH_CA']
    session = requests.Session()
    session.auth = auth
    search = session.post(f'{es_url}/{index}/_search', json={
        'size': 10000, 'track_total_hits': True, 'query': {'match_all': {}}}, verify=verify, timeout=60)
    search.raise_for_status()
    result = search.json()
    hits = result['hits']['hits']
    if (result.get('timed_out') or result['_shards']['failed'] or
            result['hits']['total']['relation'] != 'eq' or
            len(hits) != result['hits']['total']['value']):
        raise RuntimeError('Incomplete ES search; refusing rollout')
    candidates = [hit for hit in hits if hit['_id'] in ids]
    if any(hit['_source'].get('isLive') is True for hit in candidates):
        raise RuntimeError('Shorts/live conflict; refusing rollout')
    print(json.dumps({'manifest': len(ids), 'es_before': len(hits),
                      'es_candidates': len(candidates), 'ndjson_before': len(rows),
                      'ndjson_candidates': len(rows) - len(retained),
                      'regular_control_preserved': 'qsOw7Q8WJQA' in source_ids - ids},
                     ensure_ascii=False), flush=True)
    if not args.execute:
        return
    if len(candidates) < 500 or len(candidates) > 600 or len(rows) - len(retained) != len(candidates):
        raise RuntimeError('Unexpected candidate count; refusing rollout')
    backup = args.backup_dir
    if backup.exists():
        raise RuntimeError('Backup directory already exists')
    backup.mkdir(parents=True, mode=0o700)
    (backup / 'videos-es-before.json').write_text(json.dumps(hits, ensure_ascii=False))
    (backup / 'videos-ndjson-before.ndjson').write_bytes(source_path.read_bytes())
    (backup / 'shorts-manifest.json').write_text(json.dumps(sorted(ids)))
    payload = ''.join(json.dumps({'delete': {'_index': index, '_id': hit['_id']}}) + '\n'
                      for hit in candidates)
    response = session.post(f'{es_url}/_bulk', data=payload.encode(),
                            headers={'Content-Type': 'application/x-ndjson'}, verify=verify, timeout=60)
    response.raise_for_status()
    bulk = response.json()
    if bulk.get('errors') or len(bulk.get('items', [])) != len(candidates) or any(
            item['delete']['result'] != 'deleted' for item in bulk['items']):
        raise RuntimeError('Bulk deletion incomplete; backup retained')
    write_to_ndjson(retained, source_path)
    refresh = session.post(f'{es_url}/{index}/_refresh', verify=verify, timeout=60)
    refresh.raise_for_status()
    count = session.get(f'{es_url}/{index}/_count', verify=verify, timeout=60)
    count.raise_for_status()
    actual = count.json()['count']
    if actual != len(hits) - len(candidates):
        raise RuntimeError(f'Post-delete count mismatch: {actual}')
    print(json.dumps({'deleted': len(candidates), 'es_after': actual,
                      'ndjson_after': len(retained), 'backup': str(backup)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
