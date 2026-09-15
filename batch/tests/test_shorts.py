import pytest

from shorts import ShortsUnavailable, get_shorts_ids


class Downloader:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download):
        assert url.endswith('/channel/c/shorts')
        assert download is False
        return {'webpage_url': url, 'channel_id': 'c', 'entries': [
            {'id': 'a', 'url': 'https://www.youtube.com/shorts/a'},
            {'id': 'b', 'url': 'https://www.youtube.com/shorts/b'}]}


def test_short_tab_ids_are_complete_and_deduplicated():
    assert get_shorts_ids('c', Downloader) == {'a', 'b'}


@pytest.mark.parametrize('info', [None, {'entries': None}, {'webpage_url': 'https://youtube.com/channel/c/videos', 'entries': []}, {'webpage_url': 'https://youtube.com/channel/c/shorts', 'entries': [{'title': 'missing'}]}])
def test_invalid_short_tab_aborts(info):
    class Broken(Downloader):
        def extract_info(self, url, download):
            return info
    with pytest.raises(ShortsUnavailable):
        get_shorts_ids('c', Broken)
