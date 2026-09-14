from unittest.mock import Mock

import pytest
import requests

import video_membership as membership
from get_videos import collect, write_to_ndjson


def response(status, retry_after=None, text=''):
    return Mock(status_code=status, headers={'Retry-After': retry_after} if retry_after else {}, text=text)


def test_rate_limit_is_bounded_and_honors_server_wait(monkeypatch):
    waits = []
    monkeypatch.setattr(membership, '_wait', lambda delay: waits.append(delay))
    get = Mock(return_value=response(429, '90'))
    monkeypatch.setattr(membership.requests, 'get', get)
    with pytest.raises(membership.MembershipUnavailable):
        membership.get_membership('video')
    assert get.call_count == 3
    assert waits == [0, 90, 120]


def test_long_retry_after_stops_without_early_retry(monkeypatch):
    monkeypatch.setattr(membership, '_wait', lambda delay: None)
    get = Mock(return_value=response(429, '600'))
    monkeypatch.setattr(membership.requests, 'get', get)
    with pytest.raises(membership.MembershipUnavailable):
        membership.get_membership('video')
    assert get.call_count == 1


def test_transient_timeout_recovers_and_logs_no_exception_secret(monkeypatch, capsys):
    monkeypatch.setattr(membership, '_wait', lambda delay: None)
    get = Mock(side_effect=[requests.Timeout('secret URL'), response(200, text='var ytInitialPlayerResponse = {"videoDetails":{"videoId":"v"},"playabilityStatus":{"status":"OK"}};')])
    monkeypatch.setattr(membership.requests, 'get', get)
    assert membership.get_membership('v') == (False, 'watch_player_anonymous_playable')
    assert 'secret URL' not in capsys.readouterr().out


def test_minimum_spacing_includes_retries(monkeypatch):
    now = [10.0]
    sleeps = []
    def sleep(delay):
        sleeps.append(delay)
        now[0] += delay
    monkeypatch.setattr(membership.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(membership.time, 'sleep', sleep)
    monkeypatch.setattr(membership, '_next_request', 0)
    membership._wait()
    membership._wait()
    membership._wait(60)
    assert sleeps == [2, 60]


def test_collection_failure_preserves_previous_file(monkeypatch, tmp_path):
    monkeypatch.setattr('get_videos.get_video_details', lambda *args: [])
    path = tmp_path / 'videos.ndjson'
    path.write_text('previous data')
    with pytest.raises(membership.MembershipUnavailable):
        write_to_ndjson(collect(None, list('abcdef'), {}, membership=lambda _: (None, 'watch_http_403')), path)
    assert path.read_text() == 'previous data'


def test_offline_lives_do_not_trip_failure_threshold(monkeypatch):
    monkeypatch.setattr('get_videos.get_video_details', lambda *args: [])
    rows = collect(None, [str(i) for i in range(30)], {}, membership=lambda _: (None, 'watch_player_offline'))
    assert len(rows) == 30
    assert all(r['membersOnly'] is None for r in rows)
