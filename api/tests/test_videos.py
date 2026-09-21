from main import build_video_list_query


def test_video_list_query_keeps_only_completed_live_broadcasts():
    query = build_video_list_query()

    assert query["bool"]["filter"] == [
        {"term": {"membersOnly": False}},
    ]
    current, legacy = query["bool"]["should"]
    assert current == {
        "bool": {
            "filter": [
                {"term": {"isLive": True}},
                {"exists": {"field": "actualEndTime"}},
            ]
        }
    }
    assert legacy == {
        "bool": {
            "must_not": [{"exists": {"field": "isLive"}}],
            "filter": [{"exists": {"field": "actualStartTime"}}],
        }
    }
    assert query["bool"]["minimum_should_match"] == 1
