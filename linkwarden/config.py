"""Configuration utility for Linkwarden API credentials."""

import os
from typing import Tuple


def get_api_config() -> Tuple[str, str]:
    """Get Linkwarden API base URL and token from environment.

    Returns:
        Tuple of (base_url, token)

    Raises:
        ValueError: If LINKWARDEN_TOKEN is not set
    """
    base_url = os.environ.get("LINKWARDEN_URL", "https://links.kusmierz.be")
    token = os.environ.get("LINKWARDEN_TOKEN")

    if not token:
        raise ValueError("LINKWARDEN_TOKEN environment variable must be set")

    return base_url, token
