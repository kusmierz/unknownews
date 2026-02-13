"""
Shared utilities and exceptions for content fetchers.
"""

import math
from typing import Tuple
from urllib.parse import urlparse

import requests


class ContentFetchError(Exception):
    """Base exception for content fetching errors that should be raised to caller."""
    pass


class RateLimitError(ContentFetchError):
    """Raised when API rate limiting (HTTP 429) is encountered."""
    pass


def truncate_content(text: str, max_chars: int) -> Tuple[str, bool]:
    """
    Intelligently truncate text at sentence boundaries.

    Args:
        text: Text to truncate
        max_chars: Maximum characters (approximate)

    Returns:
        Tuple of (truncated text with " ..." suffix if truncated, was_truncated boolean)
    """
    if len(text) <= max_chars:
        return text, False

    # Find last sentence boundary before max_chars
    truncated = text[:max_chars]

    # Look for sentence endings: . ! ? followed by space or end
    sentence_endings = ['. ', '! ', '? ', '.\n', '!\n', '?\n']
    last_boundary = -1

    for ending in sentence_endings:
        pos = truncated.rfind(ending)
        if pos > last_boundary:
            last_boundary = pos + len(ending) - 1  # Keep the punctuation

    if last_boundary > max_chars * 0.5:  # Only use boundary if it's not too early
        return truncated[:last_boundary + 1] + " ...", True

    # Fallback: truncate at last space
    last_space = truncated.rfind(' ')
    if last_space > 0:
        return truncated[:last_space] + " ...", True

    return truncated + " ...", True


def format_duration(seconds: int) -> str:
    """
    Convert seconds to human-readable duration format.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string like "20m 15s" or "1h 5m 30s"
    """
    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60
    remaining_seconds = seconds % 60

    if minutes < 60:
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{minutes}m"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    parts = [f"{hours}h"]
    if remaining_minutes > 0:
        parts.append(f"{remaining_minutes}m")
    if remaining_seconds > 0:
        parts.append(f"{remaining_seconds}s")

    return " ".join(parts)


def format_duration_short(seconds: int) -> str:
    """Convert seconds to short rounded duration for titles.

    Examples: "54m" (was 53m33s), "~2.5h" (was 2h25m45s), "2h" (exact)
    """
    if seconds < 60:
        return f"{seconds}s"

    total_minutes = seconds / 60

    if total_minutes < 60:
        return f"{math.ceil(total_minutes)}m"

    # Round to nearest 0.5h
    total_hours = total_minutes / 60
    rounded = round(total_hours * 2) / 2

    if rounded == int(rounded):
        return f"{int(rounded)}h"
    return f"~{rounded:.1f}h"


def check_url_head(url: str, timeout: int = 5) -> dict:
    """Issue a HEAD request to check URL reachability and content type.

    Returns:
        Dict with keys:
            status (int): HTTP status code, 0 on network error
            content_type (str): Content-Type header value
            is_html (bool): True if content-type contains text/html
            fetchable (bool): True if status is 2xx/3xx (or unknown on error)
    """
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        status = resp.status_code
        content_type = resp.headers.get("content-type", "").lower()
        is_html = "text/html" in content_type or "application/xhtml+xml" in content_type
        fetchable = status < 400
        return {"status": status, "content_type": content_type, "is_html": is_html, "fetchable": fetchable}
    except Exception:
        # Network error / timeout — assume fetchable HTML so we still try
        return {"status": 0, "content_type": "", "is_html": True, "fetchable": True}


def is_video_url(url: str) -> bool:
    """
    Detect if URL points to a video platform.

    Checks domain patterns for YouTube, Vimeo, Dailymotion, Twitch.
    Fast URL-based detection without making network requests.

    Args:
        url: URL to check

    Returns:
        True if URL is from a known video platform
    """
    try:
        domain = urlparse(url).netloc.lower()
        # Remove www. prefix
        domain = domain.replace('www.', '')

        video_domains = [
            'youtube.com',
            'youtu.be',
            'vimeo.com',
            'dailymotion.com',
            'twitch.tv',
        ]

        return any(vd in domain for vd in video_domains)
    except Exception:
        return False
