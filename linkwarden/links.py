"""Linkwarden link operations — wraps raw API calls for use by commands."""

from .api import (
    create_link,
    delete_link,
    fetch_collection_links,
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
    "update_link",
]


def fetch_all_links(silent: bool = False) -> list[dict]:
    """Fetch all links from all collections.

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.

    Args:
        silent: If True, don't print progress messages
    """
    base_url, _ = get_api_config()
    collections = get_collections()
    all_links = []

    for collection in collections:
        collection_id = collection["id"]
        collection_name = collection.get("name", f"Collection {collection_id}")
        collection_url = f"{base_url}/collections/{collection_id}"
        links = fetch_collection_links(collection_id)
        for link in links:
            link["_collection_name"] = collection_name
        all_links.extend(links)
        if not silent:
            console.print(f"  [dim][link={collection_url}]{collection_name}[/link][/dim] [green]{len(links)}[/green]")

    console.print("")

    return all_links
