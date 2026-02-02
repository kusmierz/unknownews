"""Cache for LLM enrichment results.

This is a thin wrapper around the unified cache service.
"""

from typing import Optional
from .cache import get_cache, set_cache, remove_cache

CACHE_TYPE = "llm"


def get_cached(url: str) -> Optional[dict]:
    """Get cached LLM result for a URL.

    Args:
        url: URL to look up

    Returns:
        Cached enrichment result dict or None
    """
    return get_cache(url, CACHE_TYPE)


def set_cached(url: str, result: dict) -> None:
    """Cache LLM result for a URL.

    Args:
        url: URL key
        result: Enrichment result to cache
    """
    set_cache(url, result, CACHE_TYPE)


def remove_cached(url: str) -> None:
    """Remove cached LLM result for a URL after successful update.

    Args:
        url: URL to remove from cache
    """
    remove_cache(url, CACHE_TYPE)
