"""Anonymous YouTube watch-page evidence; failures are never public verdicts."""
import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests


class MembershipUnavailable(RuntimeError):
    """Stop this run without publishing an incomplete collection."""


_next_request = 0.0


def _wait(seconds=0):
    global _next_request
    delay = max(seconds, _next_request - time.monotonic(), 0)
    if delay:
        time.sleep(delay)
    _next_request = time.monotonic() + 2.0


def _retry_after(response):
    value = response.headers.get('Retry-After', '')
    try:
        return max(0, float(value))
    except (ValueError, TypeError):
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0


def classify_player(player, video_id):
    details = player.get('videoDetails', {})
    if details.get('videoId') not in (None, video_id):
        return None, 'video_id_mismatch'
    status = player.get('playabilityStatus', {})
    # Only inspect the target player's error, never titles/descriptions/recommendations.
    reason = status.get('reason', '')
    renderer = status.get('errorScreen', {}).get('playerErrorMessageRenderer', {})
    texts = [reason]
    for key in ('reason', 'subreason'):
        value = renderer.get(key, {})
        texts.append(value.get('simpleText', ''))
        texts.extend(run.get('text', '') for run in value.get('runs', []))
    message = ' '.join(texts).lower()
    if status.get('status') in ('UNPLAYABLE', 'LOGIN_REQUIRED') and any(
        marker in message for marker in (
            "join this channel to get access to members-only content",
            "this video is available to this channel's members",
        )
    ):
        return True, 'watch_player_members_only'
    if status.get('status') == 'OK' and details.get('videoId') == video_id:
        return False, 'watch_player_anonymous_playable'
    if status.get('status') == 'LIVE_STREAM_OFFLINE':
        return None, 'watch_player_offline'
    return None, 'watch_player_unknown'


def get_membership(video_id):
    delay = 0
    for attempt in range(3):
        _wait(delay)
        try:
            response = requests.get(
                'https://www.youtube.com/watch',
                params={'v': video_id, 'hl': 'en'},
                headers={'Accept-Language': 'en-US,en;q=0.9'},
                timeout=20,
            )
        except requests.RequestException as exc:
            evidence = 'watch_timeout' if isinstance(exc, requests.Timeout) else 'watch_network_error'
            print(f'Membership request: id={video_id} attempt={attempt + 1} evidence={evidence}', flush=True)
            if attempt == 2:
                return None, evidence
            delay = 5 * (2 ** attempt)
            continue
        status = response.status_code
        if status == 429 or status >= 500:
            delay = max((60 if status == 429 else 5) * (2 ** attempt), _retry_after(response))
            print(f'Membership request: id={video_id} attempt={attempt + 1} http={status}', flush=True)
            if attempt == 2 or delay > 300:
                if status == 429 or delay > 300:
                    raise MembershipUnavailable(f'Membership collection stopped: HTTP {status}; retry later')
                return None, f'watch_http_{status}'
            continue
        if status >= 400:
            print(f'Membership request: id={video_id} http={status}', flush=True)
            return None, f'watch_http_{status}'
        break
    try:
        match = re.search(r'(?:var\s+)?ytInitialPlayerResponse\s*=\s*', response.text)
        if not match:
            return None, 'watch_player_missing'
        player, _ = json.JSONDecoder().raw_decode(response.text[match.end():])
        return classify_player(player, video_id)
    except (ValueError, TypeError, AttributeError):
        return None, 'watch_parse_error'
