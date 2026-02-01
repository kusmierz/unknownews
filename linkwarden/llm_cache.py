"""Cache for LLM enrichment results."""

import json
from pathlib import Path

DEFAULT_CACHE_PATH = "data/llm_cache.json"


def load_cache(cache_path: str = DEFAULT_CACHE_PATH) -> dict:
    """Load cache from file."""
    path = Path(cache_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache: dict, cache_path: str = DEFAULT_CACHE_PATH) -> None:
    """Save cache to file."""
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def get_cached(url: str, cache_path: str = DEFAULT_CACHE_PATH) -> dict | None:
    """Get cached result for a URL."""
    cache = load_cache(cache_path)
    return cache.get(url)


def set_cached(url: str, result: dict, cache_path: str = DEFAULT_CACHE_PATH) -> None:
    """Cache result for a URL."""
    cache = load_cache(cache_path)
    cache[url] = result
    save_cache(cache, cache_path)


def remove_cached(url: str, cache_path: str = DEFAULT_CACHE_PATH) -> None:
    """Remove cached result for a URL after successful update."""
    cache = load_cache(cache_path)
    if url in cache:
        del cache[url]
        save_cache(cache, cache_path)
