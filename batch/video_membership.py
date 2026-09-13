"""Anonymous YouTube watch-page evidence; failures are never public verdicts."""
import json
import re

import requests


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
    return None, 'watch_player_unknown'


def get_membership(video_id):
    try:
        response = requests.get(
            'https://www.youtube.com/watch',
            params={'v': video_id, 'hl': 'en'},
            headers={'Accept-Language': 'en-US,en;q=0.9'},
            timeout=20,
        )
        response.raise_for_status()
        match = re.search(r'(?:var\s+)?ytInitialPlayerResponse\s*=\s*', response.text)
        if not match:
            return None, 'watch_player_missing'
        player, _ = json.JSONDecoder().raw_decode(response.text[match.end():])
        return classify_player(player, video_id)
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return None, 'watch_fetch_or_parse_failed'
