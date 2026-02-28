"""URL normalization and matching utilities."""

from urllib.parse import urlparse

# Tracking params to always strip from URLs
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "source", "fbclid", "gclid", "mc_cid", "mc_eid", "si",
}

# Domain-specific params that identify the resource (for fuzzy matching)
DOMAIN_ID_PARAMS = {
    "youtube.com": {"v", "list"},
    "www.youtube.com": {"v", "list"},
    "youtu.be": set(),  # ID is in path
    "vimeo.com": set(),  # ID is in path
    "open.spotify.com": set(),  # ID is in path
    "github.com": set(),  # ID is in path
}

# Generic ID-like params to preserve for unknown domains
GENERIC_ID_PARAMS = {"v", "id", "p", "pid", "vid", "article", "story", "post"}


def filter_query_params(query: str, keep_only: set[str] | None = None) -> str:
    """Filter query string, removing tracking params.

    Args:
        query: The query string (without leading ?)
        keep_only: If provided, only keep params in this set (in addition to removing tracking).
                   If None, keep all non-tracking params.

    Returns:
        Filtered query string (without leading ?)
    """
    if not query:
        return ""

    filtered = []
    for param in query.split("&"):
        if "=" in param:
            key = param.split("=")[0].lower()
        else:
            key = param.lower()

        # Always skip tracking params
        if key in TRACKING_PARAMS:
            continue

        # If whitelist provided, only keep params in it
        if keep_only is not None and key not in keep_only:
            continue

        filtered.append(param)

    return "&".join(filtered)


def normalize_url(url: str) -> str:
    """Normalize URL for matching: strip trailing slash, handle http/https, remove fragments and tracking params."""
    if not url:
        return ""

    parsed = urlparse(url.strip())

    # Filter query params (remove tracking, keep everything else)
    filtered_query = filter_query_params(parsed.query, keep_only=None)

    # Rebuild URL without fragment, with filtered query
    scheme = "https" if parsed.scheme in ("http", "https") else parsed.scheme
    normalized = f"{scheme}://{parsed.netloc}{parsed.path}"
    if filtered_query:
        normalized += f"?{filtered_query}"

    return normalized


def get_url_path_key(url: str) -> str:
    """Extract domain, path, and significant query params for fuzzy matching.

    Preserves ID-like query parameters for sites that use them (YouTube, etc.)
    while stripping tracking params and other noise.
    """
    if not url:
        return ""

    parsed = urlparse(url.strip())
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")

    # Determine which params to keep based on domain
    params_to_keep = DOMAIN_ID_PARAMS.get(netloc, GENERIC_ID_PARAMS)

    # Filter query params (only keep ID-like ones)
    filtered_query = filter_query_params(parsed.query, keep_only=params_to_keep)

    # Build key: netloc + path + sorted significant params
    key = f"{netloc}{path}"
    if filtered_query:
        # Sort params for consistent matching
        sorted_params = sorted(filtered_query.lower().split("&"))
        key += "?" + "&".join(sorted_params)

    return key.lower()
