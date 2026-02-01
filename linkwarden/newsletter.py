"""Newsletter index loading and management."""

import json
from .url_utils import normalize_url, get_url_path_key


def load_newsletter_index(jsonl_path: str) -> tuple[dict[str, dict], dict[str, dict]]:
    """Build indexes mapping URL -> {description, date, title}.

    Returns:
        - exact_index: normalized URL -> data
        - fuzzy_index: path key (no protocol/query) -> data
    """
    exact_index = {}
    fuzzy_index = {}
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            newsletter = json.loads(line)
            date = newsletter.get("date", "")
            for link in newsletter.get("links", []):
                url = link.get("link", "")
                data = {
                    "description": link.get("description", ""),
                    "title": link.get("title", ""),
                    "date": date,
                    "original_url": url,
                }
                normalized = normalize_url(url)
                if normalized:
                    exact_index[normalized] = data
                path_key = get_url_path_key(url)
                if path_key:
                    fuzzy_index[path_key] = data
    return exact_index, fuzzy_index
