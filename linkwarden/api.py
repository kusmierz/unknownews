"""Linkwarden API client."""
import time
import requests
from .config import get_api_config

_verbose = False


def set_verbose(enabled: int | bool) -> None:
    """Enable or disable verbose API logging."""
    global _verbose
    _verbose = enabled


def _log_request(method: str, url: str) -> None:
    """Log an API request if verbose mode is enabled."""
    if _verbose:
        # Show path only (strip base URL)
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        print(f"  [API] {method} {path}")


def _log_response(response: requests.Response, elapsed: float, item_count: int | None = None) -> None:
    """Log an API response if verbose mode is enabled."""
    if _verbose:
        msg = f"  [API] {response.status_code} ({elapsed:.1f}s)"
        if item_count is not None:
            msg += f" — {item_count} items"
        print(msg)


def fetch_all_collections() -> list[dict]:
    """Fetch all collections from Linkwarden.

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.
    """
    base_url, token = get_api_config()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{base_url}/api/v1/collections"
    _log_request("GET", url)
    t0 = time.monotonic()
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    # API returns {"response": [...]}
    result = data.get("response", [])
    _log_response(response, time.monotonic() - t0, len(result))
    return result


def iter_collection_links(collection_id: int):
    """Yield links from a collection page by page (generator).

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.

    Args:
        collection_id: Collection ID to fetch links from
    """
    base_url, token = get_api_config()
    headers = {"Authorization": f"Bearer {token}"}
    cursor = None

    while True:
        url = f"{base_url}/api/v1/search?collectionId={collection_id}"
        if cursor:
            url += f"&cursor={cursor}"
        _log_request("GET", url)
        t0 = time.monotonic()
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        result = response.json()

        data = result.get("data", {})
        links = data.get("links", [])
        _log_response(response, time.monotonic() - t0, len(links))
        if not links:
            break

        yield from links

        # Use nextCursor for pagination
        next_cursor = data.get("nextCursor")
        if not next_cursor:
            break
        cursor = next_cursor


def fetch_collection_links(collection_id: int) -> list[dict]:
    """Fetch all links from a Linkwarden collection using search API with pagination.

    Convenience wrapper around iter_collection_links() that returns a list.

    Args:
        collection_id: Collection ID to fetch links from
    """
    return list(iter_collection_links(collection_id))



def update_link(
    link: dict,
    new_name: str,
    new_url: str,
    new_description: str,
    new_tags: list[str],
    dry_run: bool = False,
) -> bool:
    """Update a Linkwarden link with name, url, description and tags.

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.

    Args:
        link: Existing link dict with id
        new_name: New link title
        new_url: New URL
        new_description: New description
        new_tags: List of tag names to add
        dry_run: If True, don't actually update
    """
    if dry_run:
        return True

    base_url, token = get_api_config()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    link_id = link["id"]

    # Build updated link object - start with existing link
    # Merge new tags with existing ones
    existing_tags = link.get("tags", [])
    existing_tag_names = {t.get("name", "") for t in existing_tags}
    tags_to_add = [{"name": t} for t in new_tags if t not in existing_tag_names]
    merged_tags = existing_tags + tags_to_add

    payload = {
        "id": link_id,
        "name": new_name,
        "url": new_url,
        "description": new_description,
        "collectionId": link.get("collectionId"),
        "collection": link.get("collection", {}),
        "tags": merged_tags,
    }

    url = f"{base_url}/api/v1/links/{link_id}"
    _log_request("PUT", url)
    t0 = time.monotonic()
    response = requests.put(url, headers=headers, json=payload)
    _log_response(response, time.monotonic() - t0)
    if not response.ok:
        print(f"    API Error: {response.status_code} - {response.text}")
    response.raise_for_status()
    return True


def delete_link(link_id: int) -> bool:
    """Delete a link from Linkwarden.

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.

    Args:
        link_id: ID of link to delete
    """
    base_url, token = get_api_config()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{base_url}/api/v1/links/{link_id}"
    _log_request("DELETE", url)
    t0 = time.monotonic()
    response = requests.delete(url, headers=headers)
    _log_response(response, time.monotonic() - t0)
    response.raise_for_status()
    return True


def fetch_link_archive(link_id: int, format_type: int) -> str | None:
    """Fetch an archived version of a link from Linkwarden.

    Args:
        link_id: Link ID
        format_type: Archive format (3=Readability JSON, 4=Monolith HTML)

    Returns:
        Response text content, or None on error/404
    """
    base_url, token = get_api_config()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{base_url}/api/v1/archives/{link_id}?format={format_type}"
    _log_request("GET", url)
    t0 = time.monotonic()
    try:
        response = requests.get(url, headers=headers)
        _log_response(response, time.monotonic() - t0)
        if not response.ok:
            return None
        return response.text
    except Exception:
        return None


def create_link(
    url: str,
    name: str,
    description: str,
    tags: list[str] | None = None,
    collection_id: int = 1,
) -> dict:
    """Create a new link in Linkwarden.

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.

    Args:
        url: The URL
        name: Link title/name
        description: Link description
        tags: List of tag names
        collection_id: Target collection ID

    Returns:
        The created link data from the API
    """
    base_url, token = get_api_config()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "name": name,
        "url": url,
        "description": description,
        "collectionId": collection_id,
        "tags": [{"name": t} for t in tags],
    }

    url = f"{base_url}/api/v1/links"
    _log_request("POST", url)
    t0 = time.monotonic()
    response = requests.post(url, headers=headers, json=payload)
    _log_response(response, time.monotonic() - t0)
    if not response.ok:
        raise Exception(f"API Error: {response.status_code} - {response.text}")
    return response.json()
