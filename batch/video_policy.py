"""Shared-list consumers that require a completed live broadcast."""


def is_completed_live(video):
    return video.get('isLive') is True and bool(video.get('actualEndTime'))
