"""Linkwarden link operations — wraps raw API calls for use by commands."""

from .api import (
    create_link,
    delete_link,
    fetch_collection_links,
    iter_collection_links,
    update_link,
)
from .collections_cache import get_collections
from .config import get_api_config
from .display import console

# Re-export API functions so commands import everything from here
__all__ = [
    "create_link",
    "delete_link",
    "fetch_all_links",
    "fetch_collection_links",
    "iter_all_links",
    "iter_collection_links",
    "update_link",
]


def iter_all_links(silent: bool = False):
    """Yield links from all collections (generator).

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.

    Args:
        silent: If True, don't print progress messages
    """
    base_url, _ = get_api_config()
    collections = get_collections()

    for collection in collections:
        collection_id = collection["id"]
        collection_name = collection.get("name", f"Collection {collection_id}")
        count = 0
        for link in iter_collection_links(collection_id):
            link["_collection_name"] = collection_name
            count += 1
            yield link
        if not silent:
            collection_url = f"{base_url}/collections/{collection_id}"
            console.print(f"  [dim][link={collection_url}]{collection_name}[/link][/dim] [green]{count}[/green]")

    if not silent:
        console.print("")


def fetch_all_links(silent: bool = False) -> list[dict]:
    """Fetch all links from all collections.

    Convenience wrapper around iter_all_links() that returns a list.

    Args:
        silent: If True, don't print progress messages
    """
    return list(iter_all_links(silent=silent))
