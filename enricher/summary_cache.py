"""Cache for LLM summary results.

This is a thin wrapper around the unified cache service.
"""

from typing import Optional
from common.cache import get_cache, set_cache, remove_cache

CACHE_TYPE = "summary"
CACHE_TTL_DAYS = 30


def get_cached(url: str) -> Optional[str]:
    """Get cached summary for a URL."""
    return get_cache(url, CACHE_TYPE, max_age_days=CACHE_TTL_DAYS)


def set_cached(url: str, summary: str) -> None:
    """Cache summary for a URL."""
    set_cache(url, summary, CACHE_TYPE, ttl_days=CACHE_TTL_DAYS)

def remove_cached(url: str) -> None:
  """Remove cached summary for a URL.

  Args:
      url: URL to remove from cache
  """
  remove_cache(url, CACHE_TYPE)
