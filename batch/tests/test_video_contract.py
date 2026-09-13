import json
from unittest.mock import Mock

import pytest
import requests

from get_videos import collect, get_video_details, load_previous, write_to_ndjson
from get_comments import load_videos
from import_videos import generate_bulk_payload_from_chunk, create_index_if_not_exists, load_index_videos
from video_membership import classify_player, get_membership
from video_policy import is_completed_live


def item(video_id, live=None):
    row = {'id': video_id, 'snippet': {'title': video_id, 'thumbnails': {},
                                     'publishedAt': '2026-09-01T00:00:00Z'}}
    if live is not None:
        row['liveStreamingDetails'] = live
    return row


def youtube(items):
    api = Mock()
    api.videos.return_value.list.return_value.execute.return_value = {'items': items}
    return api


def payload_doc(row):
    return json.loads(generate_bulk_payload_from_chunk([json.dumps(row)], 'videos').splitlines()[1])['doc']


def test_live_states_and_all_video_comment_input(tmp_path):
    api = youtube([item('upload'), item('scheduled', {}),
                   item('active', {'actualStartTime': '2026-09-01T01:00:00Z'}),
                   item('ended', {'actualStartTime': '2026-09-01T01:00:00Z',
                                  'actualEndTime': '2026-09-01T02:00:00Z'})])
    rows = get_video_details(api, ['upload', 'scheduled', 'active', 'ended'])
    assert [row['isLive'] for row in rows] == [False, True, True, True]
    assert [is_completed_live(row) for row in rows] == [False, False, False, True]
    assert rows[0]['actualStartTime'] is None and rows[0]['actualEndTime'] is None
    assert rows[-1]['actualEndTime'] == '20260901110000'
    api.videos.return_value.list.assert_called_once_with(
        part='snippet,liveStreamingDetails', id='upload,scheduled,active,ended')
    path = tmp_path / 'videos.ndjson'
    write_to_ndjson(rows, path)
    assert len(load_videos(path)) == 4
    assert len(load_previous(path)) == 4


@pytest.mark.parametrize('verdict', [True, False, None])
def test_membership_updates_preserve_status_and_unknown_flags(verdict):
    previous = {'v': {'title': 'old', 'membersOnly': True, 'isLive': True,
                       'thumbnail_created': False}}
    row = collect(youtube([item('v')]), ['v', 'v'], previous,
                  membership=lambda _: (verdict, 'test'))[0]
    stored = {'membersOnly': True, 'thumbnail_created': True}
    stored.update(payload_doc(row))
    assert stored['membersOnly'] is (True if verdict is None else verdict)
    assert stored['thumbnail_created'] is True
    assert stored['isLive'] is False
    assert row['membersOnly'] is verdict


def test_missing_api_item_does_not_clear_live_or_times():
    row = collect(youtube([]), ['v'], {'v': {'title': 'old', 'isLive': True}},
                  membership=lambda _: (None, 'unavailable'))[0]
    assert row['title'] == 'old'
    assert row['videoDetailsStatus'] == 'unavailable'
    assert 'isLive' not in payload_doc(row)
    assert 'actualStartTime' not in row


def test_api_failure_does_not_replace_file(tmp_path):
    path = tmp_path / 'videos.ndjson'
    path.write_text('previous output')
    api = youtube([])
    api.videos.return_value.list.return_value.execute.side_effect = RuntimeError('quota')
    with pytest.raises(RuntimeError):
        write_to_ndjson(collect(api, ['v'], {}), path)
    assert path.read_text() == 'previous output'


@pytest.mark.parametrize('old,new', [(True, False), (False, True)])
def test_public_scope_changes_and_idempotent_upsert(old, new):
    store = {'v': {'membersOnly': old, 'downloaded': True, 'title': 'original'}}
    row = collect(youtube([item('v')]), ['v'], {}, membership=lambda _: (new, 'test'))[0]
    payload = generate_bulk_payload_from_chunk([json.dumps(row)], 'videos').splitlines()
    for _ in range(2):
        action, update = map(json.loads, payload)
        assert update['doc_as_upsert'] is True
        store[action['update']['_id']].update(update['doc'])
    assert len(store) == 1
    assert store['v']['membersOnly'] is new and store['v']['downloaded'] is True


@pytest.mark.parametrize('status,reason,expected', [
    ('OK', '', False),
    ('UNPLAYABLE', 'Join this channel to get access to members-only content like this video, and other exclusive perks.', True),
    ('UNPLAYABLE', "This video is available to this channel's members on level: member", True),
    ('LOGIN_REQUIRED', 'Sign in to confirm your age', None),
    ('ERROR', 'Video unavailable', None),
    ('UNPLAYABLE', 'This video is private', None),
])
def test_membership_evidence(status, reason, expected):
    assert classify_player({'videoDetails': {'videoId': 'v'},
                            'playabilityStatus': {'status': status, 'reason': reason}}, 'v')[0] is expected


def test_title_is_not_membership_evidence_and_wrong_video_is_unknown():
    player = {'videoDetails': {'videoId': 'v', 'title': "This video is available to this channel's members"},
              'playabilityStatus': {'status': 'UNPLAYABLE'}}
    assert classify_player(player, 'v')[0] is None
    player['playabilityStatus']['status'] = 'OK'
    assert classify_player(player, 'other')[0] is None


def test_watch_failure_and_parser(monkeypatch):
    get = Mock(side_effect=requests.Timeout)
    monkeypatch.setattr('video_membership.requests.get', get)
    assert get_membership('v')[0] is None
    get.side_effect = None
    get.return_value.text = 'var ytInitialPlayerResponse = ' + json.dumps({
        'videoDetails': {'videoId': 'v'}, 'playabilityStatus': {'status': 'OK'}}) + ';'
    assert get_membership('v')[0] is False
    get.return_value.text = '<html>consent</html>'
    assert get_membership('v')[0] is None


def test_existing_index_mapping_and_failure(monkeypatch):
    head, put = Mock(), Mock()
    head.return_value.status_code = 200
    monkeypatch.setattr('import_videos.requests.head', head)
    monkeypatch.setattr('import_videos.requests.put', put)
    create_index_if_not_exists('videos', 'http://es')
    assert put.call_args.args[0] == 'http://es/videos/_mapping'
    assert put.call_args.kwargs['json']['properties']['membersOnly'] == {'type': 'boolean'}
    put.return_value.raise_for_status.side_effect = requests.HTTPError('mapping conflict')
    with pytest.raises(requests.HTTPError):
        create_index_if_not_exists('videos', 'http://es')


def test_index_only_backfill_scroll(monkeypatch):
    post, delete = Mock(), Mock()
    first, second = Mock(), Mock()
    first.json.return_value = {'_scroll_id': 's', 'hits': {'hits': [
        {'_id': 'index-only', '_source': {'title': 'retained'}}]}}
    second.json.return_value = {'_scroll_id': 's', 'hits': {'hits': []}}
    post.side_effect = [first, second]
    monkeypatch.setattr('import_videos.requests.post', post)
    monkeypatch.setattr('import_videos.requests.delete', delete)
    assert load_index_videos()['index-only']['title'] == 'retained'
    delete.assert_called_once()


def test_download_skips_unfinished_and_regular_videos(tmp_path, monkeypatch):
    from dl_video import download_video
    downloader = Mock()
    monkeypatch.setattr('dl_video.yt_dlp.YoutubeDL', downloader)
    for row in ({'isLive': False}, {'isLive': True}, {}):
        download_video(row, str(tmp_path))
    downloader.assert_not_called()


def test_failed_api_details_do_not_overwrite_existing_metadata():
    row = {'video_url': 'https://www.youtube.com/watch?v=v', 'title': 'stale',
           'videoDetailsStatus': 'unavailable', 'membersOnly': True}
    assert 'title' not in payload_doc(row)
    assert payload_doc(row)['membersOnly'] is True
