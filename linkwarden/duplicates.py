"""Duplicate detection utilities."""

from collections import defaultdict
from common.url_utils import normalize_url, get_url_path_key


def find_duplicates(links: list[dict]) -> tuple[list[dict], list[dict]]:
    """Find duplicate links using exact (normalized URL) and fuzzy (path key) matching.

    Returns:
        - exact_groups: list of duplicate groups with exact URL matches
        - fuzzy_groups: list of duplicate groups with fuzzy path matches
    """
    # Build exact match index: normalized_url -> [links]
    exact_index = defaultdict(list)
    for link in links:
        normalized = normalize_url(link.get("url", ""))
        if normalized:
            exact_index[normalized].append(link)

    # Extract exact duplicates (groups with 2+ links)
    exact_groups = []
    exact_link_ids = set()
    for url, group in exact_index.items():
        if len(group) > 1:
            exact_groups.append({"normalized_url": url, "links": group, "match_type": "exact"})
            exact_link_ids.update(link["id"] for link in group)

    # Build fuzzy index for remaining links (not already in exact duplicates)
    fuzzy_index = defaultdict(list)
    for link in links:
        if link["id"] not in exact_link_ids:
            path_key = get_url_path_key(link.get("url", ""))
            if path_key:
                fuzzy_index[path_key].append(link)

    # Extract fuzzy duplicates
    fuzzy_groups = [
        {"path_key": key, "links": group, "match_type": "fuzzy"}
        for key, group in fuzzy_index.items() if len(group) > 1
    ]

    return exact_groups, fuzzy_groups
