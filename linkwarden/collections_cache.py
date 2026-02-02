"""Cache for Linkwarden collections list."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

from .api import fetch_all_collections

DEFAULT_CACHE_PATH = "data/collections_cache.json"
CACHE_DURATION_DAYS = 1


def get_collections(cache_path: str = DEFAULT_CACHE_PATH) -> List[Dict[str, Any]]:
    """Get collections from cache or fetch from API if needed.

    This is the main function to use - it handles cache logic internally.
    Automatically reads base_url and token from environment variables.

    Args:
        cache_path: Path to cache file

    Returns:
        List of collection dictionaries

    Raises:
        ValueError: If LINKWARDEN_TOKEN is not set in environment
    """

    # Try cache first
    collections = get_cached_collections(cache_path)
    if collections:
        return collections

    # Cache miss or expired, fetch from API
    collections = fetch_all_collections()

    # Save to cache for next time
    set_cached_collections(collections, cache_path)

    return collections


def load_cache(cache_path: str = DEFAULT_CACHE_PATH) -> Optional[Dict[str, Any]]:
    """Load cache from file.

    Returns:
        Dict with 'timestamp' and 'collections' keys, or None if invalid/expired
    """
    path = Path(cache_path)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        # Check if cache is expired
        cached_time = datetime.fromisoformat(data.get("timestamp", ""))
        if datetime.now() - cached_time > timedelta(days=CACHE_DURATION_DAYS):
            return None

        return data
    except (json.JSONDecodeError, OSError, ValueError, KeyError):
        return None


def save_cache(collections: List[Dict[str, Any]], cache_path: str = DEFAULT_CACHE_PATH) -> None:
    """Save collections to cache with current timestamp."""
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    cache_data = {
        "timestamp": datetime.now().isoformat(),
        "collections": collections,
    }

    path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_cached_collections(cache_path: str = DEFAULT_CACHE_PATH) -> Optional[List[Dict[str, Any]]]:
    """Get cached collections if valid and not expired."""
    cache = load_cache(cache_path)
    if cache:
        return cache.get("collections")
    return None


def set_cached_collections(collections: List[Dict[str, Any]], cache_path: str = DEFAULT_CACHE_PATH) -> None:
    """Cache collections list."""
    save_cache(collections, cache_path)


def clear_cache(cache_path: str = DEFAULT_CACHE_PATH) -> None:
    """Remove cache file."""
    path = Path(cache_path)
    if path.exists():
        path.unlink()
