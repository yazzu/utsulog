import json
from unittest.mock import Mock

from get_videos import collect
from import_videos import generate_bulk_payload_from_chunk


def item(video_id):
    return {'id': video_id, 'snippet': {'title': video_id, 'thumbnails': {},
                                        'publishedAt': '2026-09-01T00:00:00Z'}}


def youtube(items):
    api = Mock()
    api.videos.return_value.list.return_value.execute.return_value = {'items': items}
    return api


def test_shorts_are_excluded_before_membership_lookup():
    membership = Mock(side_effect=lambda _: (False, 'test'))
    rows = collect(youtube([item('short'), item('regular')]), ['short', 'regular'], {},
                   membership=membership, shorts_ids={'short'})
    assert [row['video_url'] for row in rows] == ['https://www.youtube.com/watch?v=regular']
    membership.assert_called_once_with('regular')


def test_import_skips_manifest_short_even_from_old_ndjson():
    old = {'video_url': 'https://www.youtube.com/watch?v=short'}
    assert generate_bulk_payload_from_chunk([json.dumps(old)], 'videos', {'short'}) is None
