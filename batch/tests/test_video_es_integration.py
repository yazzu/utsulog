"""Opt-in: VIDEO_TEST_ES_URL=http://127.0.0.1:9200 pytest ..."""
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
import requests

import import_videos as iv


@pytest.mark.skipif(not os.getenv('VIDEO_TEST_ES_URL'), reason='Requires a development Elasticsearch')
def test_real_upsert_backfill_and_frontend_filter(monkeypatch):
    base = os.environ['VIDEO_TEST_ES_URL'].rstrip('/')
    index = 'utsulog-video-test-' + uuid4().hex
    monkeypatch.setattr(iv, 'ELASTICSEARCH_URL', base)
    monkeypatch.setattr(iv, 'INDEX_NAME', index)
    monkeypatch.setattr(iv, 'BULK_ENDPOINT', base + '/_bulk')
    monkeypatch.setattr(iv, 'ELASTICSEARCH_CA', True)
    monkeypatch.setattr(iv, 'ELASTICSEARCH_ADMIN', None)
    monkeypatch.setattr(iv, 'ELASTICSEARCH_PASSWORD', None)

    def request(method, path, **kwargs):
        response = requests.request(method, base + path, timeout=30, **kwargs)
        response.raise_for_status()
        return response.json()

    iv.create_index_if_not_exists(index, base)
    try:
        iv.create_index_if_not_exists(index, base)
        request('PUT', f'/{index}/_doc/ended', json={
            'thumbnail_created': True, 'membersOnly': True})
        rows = [
            {'video_url': 'https://www.youtube.com/watch?v=ended', 'isLive': True,
             'actualStartTime': '20260901100000', 'actualEndTime': '20260901110000'},
            {'video_url': 'https://www.youtube.com/watch?v=regular', 'isLive': False,
             'actualStartTime': None, 'actualEndTime': None},
            {'video_url': 'https://www.youtube.com/watch?v=scheduled', 'isLive': True},
            {'video_url': 'https://www.youtube.com/watch?v=active', 'isLive': True,
             'actualStartTime': '20260901120000'},
            {'video_url': 'https://www.youtube.com/watch?v=legacy',
             'actualStartTime': '20260901100000'},
        ]
        for _ in range(2):
            result = iv.send_to_elasticsearch(iv.generate_bulk_payload_from_chunk(
                list(map(json.dumps, rows)), index), 1)
            assert result.startswith('Success'), result
        for verdict in (False, True, None):
            row = {'video_url': rows[0]['video_url'], 'membersOnly': verdict}
            result = iv.send_to_elasticsearch(iv.generate_bulk_payload_from_chunk(
                [json.dumps(row)], index), 2)
            assert result.startswith('Success'), result
            stored = request('GET', f'/{index}/_doc/ended')['_source']
            assert stored['membersOnly'] is (True if verdict is None else verdict)
            assert stored['thumbnail_created'] is True
        request('POST', f'/{index}/_refresh')
        assert request('GET', f'/{index}/_count')['count'] == 5
        assert len(iv.load_index_videos()) == 5
        mapping = request('GET', f'/{index}/_mapping')[index]['mappings']['properties']
        assert all(mapping[field]['type'] == 'boolean' for field in ('membersOnly', 'isLive'))

        # The existing frontend remains a completed-broadcast search filter.
        from elasticsearch import Elasticsearch
        import main as api
        monkeypatch.setattr(api, 'VIDEOS_INDEX_NAME', index)
        with Elasticsearch(base) as es:
            req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(es=es)))
            assert {v['videoId'] for v in api.get_videos(req)['videos']} == {'ended', 'legacy'}
    finally:
        request('DELETE', '/' + index)
