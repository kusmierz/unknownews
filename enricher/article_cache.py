"""Cache for trafilatura article content.

This is a thin wrapper around the unified cache service.
Caches extracted article content to avoid re-downloading.
"""

from typing import Optional, Dict, Any
from common.cache import get_cache, set_cache, remove_cache

CACHE_TYPE = "article"
CACHE_TTL_DAYS = 180


def get_cached(url: str) -> Optional[Dict[str, Any]]:
    """Get cached article content for a URL."""
    return get_cache(url, CACHE_TYPE, max_age_days=CACHE_TTL_DAYS)


def set_cached(url: str, data: Dict[str, Any]) -> None:
    """Cache article content for a URL."""
    set_cache(url, data, CACHE_TYPE, ttl_days=CACHE_TTL_DAYS)

def remove_cached(url: str) -> None:
  """Remove cached LLM result for a URL after successful update.

  Args:
      url: URL to remove from cache
  """
  remove_cache(url, CACHE_TYPE)
