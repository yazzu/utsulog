import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from patch_script import remove_unfinished_lives as cleanup


def response(payload):
    result = Mock()
    result.json.return_value = payload
    return result


def test_dry_run_lists_candidates_without_deleting(monkeypatch, capsys):
    post = Mock(return_value=response({"hits": {"total": {"value": 1}, "hits": [
        {"_id": "scheduled", "_source": {"title": "upcoming"}}
    ]}}))
    monkeypatch.setattr(cleanup.requests, "post", post)
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://es")
    monkeypatch.setenv("VIDEOS_INDEX_NAME", "videos")

    assert cleanup.main([]) == 0
    assert post.call_count == 1
    assert "scheduled\tupcoming" in capsys.readouterr().out
    assert post.call_args.kwargs["json"]["query"] == cleanup.unfinished_live_query()
    assert "sort" not in post.call_args.kwargs["json"]


def test_execute_requires_matching_expected_count(monkeypatch):
    monkeypatch.setattr(cleanup, "find_candidates", lambda *_: [{"_id": "active"}])
    delete = Mock()
    monkeypatch.setattr(cleanup, "delete_candidates", delete)
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://es")
    monkeypatch.setenv("VIDEOS_INDEX_NAME", "videos")

    assert cleanup.main(["--execute", "--expected-count", "2"]) == 1
    delete.assert_not_called()


def test_execute_deletes_only_discovered_ids(monkeypatch):
    monkeypatch.setattr(cleanup, "find_candidates", lambda *_: [
        {"_id": "scheduled"}, {"_id": "active"}
    ])
    delete = Mock(return_value=2)
    monkeypatch.setattr(cleanup, "delete_candidates", delete)
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://es/")
    monkeypatch.setenv("VIDEOS_INDEX_NAME", "videos")

    assert cleanup.main(["--execute", "--expected-count", "2"]) == 0
    delete.assert_called_once_with("http://es", "videos", ["scheduled", "active"])


def test_execute_requires_expected_count():
    with pytest.raises(SystemExit):
        cleanup.parse_args(["--execute"])
