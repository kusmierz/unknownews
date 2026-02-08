"""Linkwarden API client."""
import requests
from .config import get_api_config


def fetch_all_collections() -> list[dict]:
    """Fetch all collections from Linkwarden.

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.
    """
    base_url, token = get_api_config()
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{base_url}/api/v1/collections", headers=headers)
    response.raise_for_status()
    data = response.json()
    # API returns {"response": [...]}
    return data.get("response", [])


def fetch_collection_links(collection_id: int) -> list[dict]:
    """Fetch all links from a Linkwarden collection using search API with pagination.

    Automatically reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment.

    Args:
        collection_id: Collection ID to fetch links from
    """
    base_url, token = get_api_config()
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
    response = requests.put(url, headers=headers, json=payload)
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
    response = requests.delete(f"{base_url}/api/v1/links/{link_id}", headers=headers)
    response.raise_for_status()
    return True


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

    response = requests.post(f"{base_url}/api/v1/links", headers=headers, json=payload)
    if not response.ok:
        raise Exception(f"API Error: {response.status_code} - {response.text}")
    return response.json()
