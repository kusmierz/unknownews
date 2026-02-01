"""Linkwarden API client."""

import requests
from .display import console


def fetch_all_collections(base_url: str, token: str) -> list[dict]:
    """Fetch all collections from Linkwarden."""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{base_url}/api/v1/collections", headers=headers)
    response.raise_for_status()
    data = response.json()
    # API returns {"response": [...]}
    return data.get("response", [])


def fetch_collection_links(base_url: str, collection_id: int, token: str) -> list[dict]:
    """Fetch all links from a Linkwarden collection using search API with pagination."""
    headers = {"Authorization": f"Bearer {token}"}
    all_links = []
    cursor = None

    while True:
        url = f"{base_url}/api/v1/search?collectionId={collection_id}"
        if cursor:
            url += f"&cursor={cursor}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        result = response.json()

        data = result.get("data", {})
        links = data.get("links", [])
        if not links:
            break

        all_links.extend(links)

        # Use nextCursor for pagination
        next_cursor = data.get("nextCursor")
        if not next_cursor:
            break
        cursor = next_cursor

    return all_links


def fetch_all_links(base_url: str, token: str, silent: bool = False) -> list[dict]:
    """Fetch all links from all collections."""
    collections = fetch_all_collections(base_url, token)
    all_links = []

    for collection in collections:
        collection_id = collection["id"]
        collection_name = collection.get("name", f"Collection {collection_id}")
        collection_url = f"{base_url}/collections/{collection_id}"
        links = fetch_collection_links(base_url, collection_id, token)
        for link in links:
            link["_collection_name"] = collection_name
        all_links.extend(links)
        if not silent:
            console.print(f"  [dim][link={collection_url}]{collection_name}[/link][/dim] [green]{len(links)}[/green]")

    return all_links


def update_link(
    base_url: str,
    link: dict,
    new_name: str,
    new_url: str,
    new_description: str,
    new_tags: list[str],
    token: str,
    dry_run: bool = False,
) -> bool:
    """Update a Linkwarden link with name, url, description and tags."""
    if dry_run:
        return True

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
    response = requests.put(url, headers=headers, json=payload)
    if not response.ok:
        print(f"    API Error: {response.status_code} - {response.text}")
    response.raise_for_status()
    return True


def delete_link(base_url: str, link_id: int, token: str) -> bool:
    """Delete a link from Linkwarden."""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.delete(f"{base_url}/api/v1/links/{link_id}", headers=headers)
    response.raise_for_status()
    return True


def create_link(
    base_url: str,
    name: str,
    url: str,
    description: str,
    tags: list[str],
    collection_id: int,
    token: str,
) -> dict:
    """Create a new link in Linkwarden.

    Args:
        base_url: Linkwarden API base URL
        name: Link title/name
        url: The URL
        description: Link description
        tags: List of tag names
        collection_id: Target collection ID
        token: API token

    Returns:
        The created link data from the API
    """
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

    response = requests.post(f"{base_url}/api/v1/links", headers=headers, json=payload)
    if not response.ok:
        raise Exception(f"API Error: {response.status_code} - {response.text}")
    return response.json()
