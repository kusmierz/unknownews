"""Unified cache service for LLM results, collections, and other data."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

CACHE_DIR = Path("cache")


def _ensure_cache_dir():
    """Ensure cache directory exists."""
    CACHE_DIR.mkdir(exist_ok=True)


def _get_cache_path(cache_type: str) -> Path:
    """Get cache file path for a given cache type.

    Args:
        cache_type: Type of cache (e.g., 'llm', 'collections')

    Returns:
        Path to cache file
    """
    return CACHE_DIR / f"{cache_type}.json"


def _load_cache_file(cache_type: str) -> dict:
    """Load entire cache file for a given type.

    Returns:
        Dict with cache data, or empty dict if file doesn't exist
    """
    cache_path = _get_cache_path(cache_type)
    if not cache_path.exists():
        return {}

    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache_file(cache_type: str, data: dict) -> None:
    """Save entire cache file for a given type."""
    _ensure_cache_dir()
    cache_path = _get_cache_path(cache_type)
    cache_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def get_cache(key: str, cache_type: str, max_age_days: Optional[int] = None) -> Optional[Any]:
    """Get cached value by key.

    Args:
        key: Cache key (e.g., URL for LLM, or 'data' for collections)
        cache_type: Type of cache (e.g., 'llm', 'collections')
        max_age_days: Maximum age in days. If provided, check timestamp and invalidate if too old.

    Returns:
        Cached value or None if not found/expired
    """
    cache_data = _load_cache_file(cache_type)

    if key not in cache_data:
        return None

    entry = cache_data[key]

    # Check expiration if max_age_days is set
    if max_age_days is not None and isinstance(entry, dict) and "timestamp" in entry:
        try:
            cached_time = datetime.fromisoformat(entry["timestamp"])
            if datetime.now() - cached_time > timedelta(days=max_age_days):
                # Expired, remove it
                del cache_data[key]
                _save_cache_file(cache_type, cache_data)
                return None
        except (ValueError, KeyError):
            pass

    # Return the value (for timestamped entries, return the 'value' field)
    if isinstance(entry, dict) and "value" in entry:
        return entry["value"]
    return entry


def set_cache(key: str, value: Any, cache_type: str, ttl_days: Optional[int] = None) -> None:
    """Set cache value with optional TTL.

    Args:
        key: Cache key
        value: Value to cache
        cache_type: Type of cache
        ttl_days: Time-to-live in days. If provided, adds timestamp for expiration checking.
    """
    cache_data = _load_cache_file(cache_type)

    if ttl_days is not None:
        # Store with timestamp for TTL
        cache_data[key] = {
            "timestamp": datetime.now().isoformat(),
            "value": value
        }
    else:
        # Store value directly
        cache_data[key] = value

    _save_cache_file(cache_type, cache_data)


def remove_cache(key: str, cache_type: str) -> None:
    """Remove specific cache entry.

    Args:
        key: Cache key to remove
        cache_type: Type of cache
    """
    cache_data = _load_cache_file(cache_type)
    if key in cache_data:
        del cache_data[key]
        _save_cache_file(cache_type, cache_data)


def clear_cache_type(cache_type: str) -> None:
    """Clear all cache for a specific type.

    Args:
        cache_type: Type of cache to clear
    """
    cache_path = _get_cache_path(cache_type)
    if cache_path.exists():
        cache_path.unlink()
