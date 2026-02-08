"""
Shared utilities and exceptions for content fetchers.
"""

from typing import Tuple
from urllib.parse import urlparse


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
