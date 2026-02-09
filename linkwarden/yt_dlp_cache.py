"""Cache for yt-dlp video info results.

This is a thin wrapper around the unified cache service.
Caches full yt-dlp info_dict to avoid hitting YouTube rate limits.
"""

from typing import Optional, Dict, Any
from .cache import get_cache, set_cache, remove_cache

CACHE_TYPE = "yt_dlp"
CACHE_TTL_DAYS = 7  # Video metadata rarely changes


def get_cached(url: str) -> Optional[Dict[str, Any]]:
    """Get cached yt-dlp info for a URL.

    Args:
        url: Video URL to look up

    Returns:
        Cached yt-dlp info dict or None
    """
    return get_cache(url, CACHE_TYPE, max_age_days=CACHE_TTL_DAYS)


def set_cached(url: str, info_dict: Dict[str, Any]) -> None:
    """Cache yt-dlp info for a URL.

    Args:
        url: Video URL key
        info_dict: yt-dlp info dictionary to cache
    """
    set_cache(url, info_dict, CACHE_TYPE, ttl_days=CACHE_TTL_DAYS)


def remove_cached(url: str) -> None:
  """Remove cached LLM result for a URL after successful update.

  Args:
      url: URL to remove from cache
  """
  remove_cache(url, CACHE_TYPE)
