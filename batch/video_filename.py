from pathvalidate import sanitize_filename


# Most Linux filesystems limit a single path component to 255 bytes. yt-dlp
# appends temporary suffixes such as ".f243.webm.part", so keep some headroom.
MAX_VIDEO_FILENAME_BYTES = 200


def _truncate_utf8(value, max_bytes):
    """Truncate text without splitting a UTF-8 encoded character."""
    return value.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def build_video_filename(actual_start_time, video_id, title):
    """Build a filesystem-safe video filename with room for yt-dlp suffixes."""
    prefix = f"{actual_start_time}_[{video_id}]_"
    extension = ".mp4"
    title_budget = MAX_VIDEO_FILENAME_BYTES - len((prefix + extension).encode("utf-8"))
    sanitized_title = sanitize_filename(title or "")
    truncated_title = _truncate_utf8(sanitized_title, max(0, title_budget)).rstrip()
    return f"{prefix}{truncated_title}{extension}"
