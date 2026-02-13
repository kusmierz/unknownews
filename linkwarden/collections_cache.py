"""Cache for Linkwarden collections list.

This is a thin wrapper around the unified cache service.
"""

from typing import List, Dict, Any

from .api import fetch_all_collections
from .cache import get_cache, set_cache, clear_cache_type

CACHE_TYPE = "collections"
CACHE_KEY = "data"  # Single key for all collections
CACHE_TTL_DAYS = 1


def get_collections() -> List[Dict[str, Any]]:
    """Get collections from cache or fetch from API if needed.

    This is the main function to use - it handles cache logic internally.
    Automatically reads base_url and token from environment variables.

    Returns:
        List of collection dictionaries

    Raises:
        ValueError: If LINKWARDEN_TOKEN is not set in environment
    """
    # Try cache first (with 1-day expiration)
    collections = get_cache(CACHE_KEY, CACHE_TYPE, max_age_days=CACHE_TTL_DAYS)
    if collections:
        return collections

    # Cache miss or expired, fetch from API
    collections = fetch_all_collections()

    # Save to cache with TTL
    set_cache(CACHE_KEY, collections, CACHE_TYPE, ttl_days=CACHE_TTL_DAYS)

    return collections


def clear_collections_cache() -> None:
    """Clear the collections cache."""
    clear_cache_type(CACHE_TYPE)
