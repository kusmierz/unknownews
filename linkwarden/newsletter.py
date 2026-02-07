"""Newsletter index loading and management."""

import json
import os
from typing import Any, TypedDict

from .url_utils import normalize_url, get_url_path_key

JSONL_PATH = "data/newsletters.jsonl"


class LinkIndexEntry(TypedDict):
    description: str
    title: str
    date: str
    original_url: str


def load_newsletter_index(
    jsonl_path: str | None = None,
) -> tuple[dict[str, LinkIndexEntry], dict[str, LinkIndexEntry]]:
    """Build indexes mapping URL -> {description, date, title}.

    Returns:
        - exact_index: normalized URL -> data
        - fuzzy_index: path key (no protocol/query) -> data
    """

    if not jsonl_path:
        jsonl_path = JSONL_PATH

    if not os.path.exists(jsonl_path):
      raise FileNotFoundError

    exact_index: dict[str, LinkIndexEntry] = {}
    fuzzy_index: dict[str, LinkIndexEntry] = {}

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            newsletter: dict[str, Any] = json.loads(line)
            date = newsletter.get("date", "")
            for link in newsletter.get("links", []):
                url = link.get("link", "")
                data: LinkIndexEntry = {
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
