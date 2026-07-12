from datetime import datetime, timezone, timedelta

from main import build_datetime_range_filters

JST = timezone(timedelta(hours=9))


def test_returns_empty_list_when_no_dates_given():
    assert build_datetime_range_filters(None, None) == []


def test_date_from_only_builds_gte_filter():
    filters = build_datetime_range_filters("2026-07-10T22:00:00", None)
    expected_ts = int(datetime(2026, 7, 10, 22, 0, 0, tzinfo=JST).timestamp() * 1000)
    assert filters == [{"range": {"timestamp": {"gte": expected_ts}}}]


def test_date_to_only_builds_lte_filter_without_plus_one_day():
    filters = build_datetime_range_filters(None, "2026-07-10T23:00:00")
    expected_ts = int(datetime(2026, 7, 10, 23, 0, 0, tzinfo=JST).timestamp() * 1000)
    assert filters == [{"range": {"timestamp": {"lte": expected_ts}}}]


def test_date_from_and_date_to_build_both_filters_in_order():
    filters = build_datetime_range_filters("2026-07-10T00:00:00", "2026-07-10T23:59:59")
    expected_from = int(datetime(2026, 7, 10, 0, 0, 0, tzinfo=JST).timestamp() * 1000)
    expected_to = int(datetime(2026, 7, 10, 23, 59, 59, tzinfo=JST).timestamp() * 1000)
    assert filters == [
        {"range": {"timestamp": {"gte": expected_from}}},
        {"range": {"timestamp": {"lte": expected_to}}},
    ]


def test_same_minute_from_and_to_yield_non_zero_range():
    # フロントエンドが秒を :00 / :59 に固定補完するため、同じ分を指定しても幅を持つ
    filters = build_datetime_range_filters("2026-07-10T22:00:00", "2026-07-10T22:00:59")
    gte = filters[0]["range"]["timestamp"]["gte"]
    lte = filters[1]["range"]["timestamp"]["lte"]
    assert lte > gte


def test_invalid_date_from_is_ignored():
    filters = build_datetime_range_filters("not-a-date", "2026-07-10T23:59:59")
    assert len(filters) == 1
    assert "lte" in filters[0]["range"]["timestamp"]


def test_invalid_date_to_is_ignored():
    filters = build_datetime_range_filters("2026-07-10T00:00:00", "not-a-date")
    assert len(filters) == 1
    assert "gte" in filters[0]["range"]["timestamp"]


def test_naive_datetime_is_interpreted_as_jst_regardless_of_system_timezone():
    # サーバープロセスのシステムタイムゾーンに関わらず、オフセットの無い日時文字列は
    # 常にJST(Asia/Tokyo)として解釈されることを保証する回帰テスト。
    # 期待値はテスト対象のコードパスを再利用せず、独立して算出する。
    filters = build_datetime_range_filters("2026-07-10T22:00:00", None)
    expected_ts = int(
        datetime(2026, 7, 10, 22, 0, 0, tzinfo=timezone(timedelta(hours=9))).timestamp() * 1000
    )
    assert filters == [{"range": {"timestamp": {"gte": expected_ts}}}]
    assert expected_ts == 1783688400000
