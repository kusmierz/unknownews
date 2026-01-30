#!/usr/bin/env python3
"""
Linkwarden tools: sync newsletter descriptions and remove duplicate links.

Usage:
    # List all links grouped by collection
    python linkwarden_sync.py list                    # list all links
    python linkwarden_sync.py list --collection 14   # list links from specific collection

    # Sync newsletter descriptions to Linkwarden (all collections by default)
    python linkwarden_sync.py sync                    # sync all collections
    python linkwarden_sync.py sync --collection 14    # sync specific collection
    python linkwarden_sync.py sync --dry-run          # preview without updating

    # Remove duplicates across all collections (keeps oldest link in each group)
    python linkwarden_sync.py remove-duplicates --dry-run  # preview deletions
    python linkwarden_sync.py remove-duplicates            # actually delete duplicates

    # Backward compatibility (defaults to sync)
    python linkwarden_sync.py --dry-run               # same as: sync --dry-run
"""

import argparse
from collections import defaultdict
import difflib
import json
import os
import shutil
import sys
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
import hashlib

from rich.console import Console
from rich.markup import escape
from rich.text import Text

# Colors for tags (visually distinct, readable on dark backgrounds)
TAG_COLORS = [
    "bright_magenta", "bright_cyan", "bright_green", "bright_yellow",
    "bright_blue", "bright_red", "magenta", "cyan", "green", "yellow",
    "blue", "red", "deep_pink3", "dark_orange", "chartreuse3", "turquoise2",
]


def get_tag_color(tag_name: str) -> str:
    """Get a consistent color for a tag based on its name."""
    tag_hash = int(hashlib.md5(tag_name.encode()).hexdigest(), 16)
    return TAG_COLORS[tag_hash % len(TAG_COLORS)]

console = Console()

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


def show_diff(old: str, new: str, indent: str = "      ") -> None:
    """Show diff with highlighted changes using rich."""
    matcher = difflib.SequenceMatcher(None, old, new)

    old_text = Text()
    old_text.append(f"{indent}- ", style="red")
    new_text = Text()
    new_text.append(f"{indent}+ ", style="green")

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            old_text.append(old[i1:i2])
            new_text.append(new[j1:j2])
        elif tag == "replace":
            old_text.append(old[i1:i2], style="bold red on dark_red")
            new_text.append(new[j1:j2], style="bold green on dark_green")
        elif tag == "delete":
            old_text.append(old[i1:i2], style="bold red on dark_red")
        elif tag == "insert":
            new_text.append(new[j1:j2], style="bold green on dark_green")

    console.print(old_text)
    console.print(new_text)


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


def fetch_all_collections(base_url: str, token: str) -> list[dict]:
    """Fetch all collections from Linkwarden."""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{base_url}/api/v1/collections", headers=headers)
    response.raise_for_status()
    data = response.json()
    # API returns {"response": [...]}
    return data.get("response", [])


def fetch_all_links(base_url: str, token: str) -> list[dict]:
    """Fetch all links from all collections."""
    collections = fetch_all_collections(base_url, token)
    all_links = []
    for collection in collections:
        collection_id = collection["id"]
        collection_name = collection.get("name", f"Collection {collection_id}")
        collection_url = f"{base_url}/collections/{collection_id}"
        console.print(f"  Fetching [{collection_id:3} # [cyan][link={collection_url}]{collection_name}[/link][/cyan]]... ", end="")
        links = fetch_collection_links(base_url, collection_id, token)
        # Add collection info to each link for reporting
        for link in links:
            link["_collection_name"] = collection_name
        all_links.extend(links)
        console.print(f"[green]{len(links)}[/green] links")
    return all_links


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


def print_duplicate_report(exact_groups: list[dict], fuzzy_groups: list[dict], total_links: int, base_url: str, dry_run: bool = False) -> None:
    """Display duplicate groups showing which links will be kept vs deleted."""
    exact_dup_count = sum(len(g["links"]) for g in exact_groups)
    fuzzy_dup_count = sum(len(g["links"]) for g in fuzzy_groups)
    total_to_delete = sum(len(g["links"]) - 1 for g in exact_groups + fuzzy_groups)

    # Summary statistics
    action_word = "Would delete" if dry_run else "Will delete"
    console.print("\n[bold]=== Duplicate Report ===[/bold]")
    console.print(f"Total links:      {total_links}")
    console.print(f"Exact duplicates: [red]{exact_dup_count}[/red] links in [red]{len(exact_groups)}[/red] groups")
    console.print(f"Fuzzy duplicates: [yellow]{fuzzy_dup_count}[/yellow] links in [yellow]{len(fuzzy_groups)}[/yellow] groups")
    console.print(f"{action_word}:    [bold red]{total_to_delete}[/bold red] links (keeping oldest in each group)")

    if not exact_groups and not fuzzy_groups:
        console.print("\n[green]No duplicates found![/green]")
        return

    # Display both exact and fuzzy groups
    sections = [
        (exact_groups, "Exact Duplicates", "normalized_url", "red"),
        (fuzzy_groups, "Fuzzy Duplicates", "path_key", "yellow"),
    ]
    for groups, title, key_field, color in sections:
        if not groups:
            continue
        console.print(f"\n[bold {color}]--- {title} ---[/bold {color}]")
        for i, group in enumerate(groups, 1):
            links = sorted(group["links"], key=lambda x: x.get("id", 0))
            console.print(f"\n[bold][{i}][/bold] {group[key_field]} ([{color}]{len(links)} links[/{color}])")
            first_url = links[0].get("url", "") if links else ""
            for j, link in enumerate(links):
                link_id = link.get("id", "?")
                name = link.get("name", "Untitled")[:60]
                collection = link.get("_collection_name", "?")
                link_url = link.get("url", "")
                link_ui_url = f"{base_url}/preserved/{link_id}?format=4"
                if j == 0:
                    console.print(f"    [green]KEEP[/green]   # {link_id:5} | [{collection}] | [link={link_ui_url}]{name}[/link]")
                else:
                    console.print(f"    [red]DELETE[/red] # {link_id:5} | [{collection}] | [link={link_ui_url}]{name}[/link]")
                    if link_url != first_url:
                        show_diff(first_url, link_url, indent="           ")


def delete_link(base_url: str, link_id: int, token: str) -> bool:
    """Delete a link from Linkwarden."""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.delete(f"{base_url}/api/v1/links/{link_id}", headers=headers)
    response.raise_for_status()
    return True


def list_links(base_url: str, token: str, collection_id: int | None = None) -> None:
    """List all links grouped by collection."""
    # Fetch links
    if collection_id is not None:
        console.print(f"Fetching links from collection #{collection_id}...")
        links = fetch_collection_links(base_url, collection_id, token)
        # Add collection info manually since fetch_collection_links doesn't include it
        collections = fetch_all_collections(base_url, token)
        collection_name = next(
            (c.get("name", f"Collection {collection_id}") for c in collections if c["id"] == collection_id),
            f"Collection {collection_id}"
        )
        for link in links:
            link["_collection_name"] = collection_name
    else:
        console.print("Fetching links from all collections...")
        links = fetch_all_links(base_url, token)

    console.print(f"\nTotal: [bold]{len(links)}[/bold] links\n")

    if not links:
        console.print("[yellow]No links found.[/yellow]")
        return

    # Group links by collection
    by_collection = defaultdict(list)
    for link in links:
        collection_name = link.get("_collection_name", "Unknown")
        by_collection[collection_name].append(link)

    # Calculate available widths
    terminal_width = shutil.get_terminal_size().columns or 120
    # Line 1: "  #12345 Link Name  [tags]" - name can be generous
    link_name_max = int(min(80, terminal_width - 30))  # Leave room for ID and tags
    # Line 2: "         Description..." - indent is 9 spaces
    desc_max_width = terminal_width - 10  # 9 for indent + 1 buffer

    # Display links grouped by collection
    for collection_name, collection_links in sorted(by_collection.items()):
        collection_url = f"{base_url}/collections/{collection_id}"
        console.print(f"[bold][[link={collection_url}]{escape(collection_name)}[/link] ({len(collection_links)} links)][/bold]")
        for link in sorted(collection_links, key=lambda x: x.get("id", 0)):
            link_id = link.get("id", "?")
            name = (link.get("name") or "").strip()
            is_untitled = not name or name == "Just a moment..."
            if is_untitled:
                name = "Untitled"
            description = link.get("description", "") or ""
            tags = [t.get("name", "") for t in link.get("tags", []) if t.get("name")]
            link_ui_url = f"{base_url}/preserved/{link_id}?format=4"

            # Truncate name if too long
            if len(name) > link_name_max:
                name = name[:link_name_max - 3] + "..."

            # Truncate description to fit terminal
            if len(description) > desc_max_width:
                description = description[:desc_max_width - 3] + "..."
            # Replace newlines with spaces for single-line display
            description = description.replace("\n", " ").strip()

            # Line 1: ID, name, tags
            line1 = Text()
            line1.append(f"  #{link_id:<5} ", style="cyan")
            name_style = f"italic link {link_ui_url}" if is_untitled else f"link {link_ui_url}"
            line1.append(name, style=name_style)
            if tags:
                line1.append("  ")
                for i, tag in enumerate(tags):
                    if i > 0:
                        line1.append(" ")
                    line1.append(f"[{tag}]", style=f"dim {get_tag_color(tag)}")
            console.print(line1)

            # Line 2: description (indented)
            if description:
                line2 = Text()
                line2.append("         ")  # Align with name (9 spaces)
                line2.append(description, style="dim")
                console.print(line2)

            console.print()  # Empty line between links
        console.print()  # Extra line between collections

    # Check for duplicates
    exact_groups, fuzzy_groups = find_duplicates(links)
    total_duplicates = sum(len(g["links"]) - 1 for g in exact_groups + fuzzy_groups)
    if total_duplicates > 0:
        console.print(f"[yellow]Found {total_duplicates} duplicate links.[/yellow]")
        console.print("[dim]Run 'python linkwarden_sync.py remove-duplicates --dry-run' to preview removal[/dim]")
        console.print("[dim]Run 'python linkwarden_sync.py remove-duplicates' to remove them[/dim]")


def remove_duplicates(base_url: str, token: str, dry_run: bool = False) -> None:
    """Fetch all links across all collections, find duplicates, and remove them."""
    action_word = "[DRY RUN] " if dry_run else ""
    console.print(f"{action_word}Finding and removing duplicates across all collections...")
    console.print("Fetching collections...")

    all_links = fetch_all_links(base_url, token)
    console.print(f"\nTotal: [bold]{len(all_links)}[/bold] links")

    exact_groups, fuzzy_groups = find_duplicates(all_links)

    # Display what will be kept/deleted
    print_duplicate_report(exact_groups, fuzzy_groups, len(all_links), base_url, dry_run=dry_run)

    if not exact_groups and not fuzzy_groups:
        return

    # Collect all links to delete (all but the oldest in each group)
    links_to_delete = []
    for group in exact_groups + fuzzy_groups:
        sorted_links = sorted(group["links"], key=lambda x: x.get("id", 0))
        # Keep the first (oldest) link, delete the rest
        links_to_delete.extend(sorted_links[1:])

    if not links_to_delete:
        return

    # Delete duplicates
    console.print(f"\n{action_word}Deleting {len(links_to_delete)} duplicate links...")
    deleted = 0
    errors = 0

    for link in links_to_delete:
        link_id = link.get("id")
        link_url = link.get("url", "")
        collection = link.get("_collection_name", "?")

        if dry_run:
            console.print(f"  [dim]Would delete[/dim] # {link_id:5} | [{collection}] | {link_url[:60]}")
        else:
            try:
                delete_link(base_url, link_id, token)
                console.print(f"  [red]Deleted[/red] # {link_id:5} | [{collection}] | {link_url[:60]}")
                deleted += 1
            except Exception as e:
                console.print(f"  [bold red]Error deleting ID {link_id:5}:[/bold red] {e}")
                errors += 1

    # Summary
    console.print(f"\n[bold]{action_word}Summary:[/bold]")
    console.print(f"  [red]Deleted: {deleted}[/red]")
    if errors:
        console.print(f"  [bold red]Errors: {errors}[/bold red]")


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


def sync_links(
    base_url: str,
    jsonl_path: str,
    token: str,
    collection_id: int | None = None,
    dry_run: bool = False,
    limit: int = 0,
) -> None:
    """Main sync logic: match URLs and update Linkwarden.

    If collection_id is None, syncs all collections.
    """
    # Load newsletter index
    console.print(f"Loading newsletter index from {jsonl_path}...")
    newsletter_index, newsletter_fuzzy_index = load_newsletter_index(jsonl_path)
    console.print(f"  Indexed {len(newsletter_index)} unique links from newsletters")

    # Fetch Linkwarden links
    if collection_id is not None:
        console.print(f"\nFetching links from collection #{collection_id}...")
        linkwarden_links = fetch_collection_links(base_url, collection_id, token)
        console.print(f"  Fetched {len(linkwarden_links)} links")
    else:
        console.print("\nFetching links from all collections...")
        linkwarden_links = fetch_all_links(base_url, token)
        console.print(f"\nTotal: [bold]{len(linkwarden_links)}[/bold] links")

    # Match and prepare updates
    matches = []
    unmatched_urls = []
    for lw_link in linkwarden_links:
        lw_url = lw_link.get("url", "")
        normalized_lw_url = normalize_url(lw_url)

        if normalized_lw_url in newsletter_index:
            nl_data = newsletter_index[normalized_lw_url]
            matches.append({
                "linkwarden": lw_link,
                "newsletter": nl_data,
                "match_type": "exact",
            })
        else:
            # Try fuzzy matching
            path_key = get_url_path_key(lw_url)
            if path_key in newsletter_fuzzy_index:
                nl_data = newsletter_fuzzy_index[path_key]
                matches.append({
                    "linkwarden": lw_link,
                    "newsletter": nl_data,
                    "match_type": "fuzzy",
                })
            else:
                unmatched_urls.append(lw_url)

    exact_count = sum(1 for m in matches if m["match_type"] == "exact")
    fuzzy_count = sum(1 for m in matches if m["match_type"] == "fuzzy")
    console.print(f"\n[green]Exact: {exact_count}[/green] | [cyan]Fuzzy: {fuzzy_count}[/cyan] | [yellow]Unmatched: {len(unmatched_urls)}[/yellow]")

    if not matches:
        print("No matches found. Nothing to update.")
    else:
        # Process updates
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing updates...\n")
        updated = 0
        skipped = 0

        for match in matches:
            lw_link = match["linkwarden"]
            nl_data = match["newsletter"]
            match_type = match["match_type"]

            link_id = lw_link.get("id")
            link_name = lw_link.get("name", "Untitled")
            link_url = lw_link.get("url", "")
            normalized_url = normalize_url(link_url)
            existing_desc = lw_link.get("description", "") or ""
            existing_tags = {tag.get("name", "") for tag in lw_link.get("tags", [])}

            nl_title = nl_data.get("title", "")
            nl_description = nl_data.get("description", "")
            nl_date = nl_data.get("date", "")
            nl_link = nl_data.get("original_url", "")

            # Prepare tags
            tags_to_add = ["unknow"]
            if nl_date:
                tags_to_add.append(nl_date)

            # Check what needs updating
            new_tags = [t for t in tags_to_add if t not in existing_tags]
            description_needs_update = nl_description and nl_description not in existing_desc
            # Name needs update only if newsletter title exists, differs from current name,
            # and the current name doesn't already start with the newsletter title (already synced)
            name_needs_update = (
                nl_title
                and link_name
                and link_name != nl_title
                and not link_name.startswith(nl_title)
            )
            # URL needs update if normalized version differs from current
            url_needs_update = normalized_url and normalized_url != link_url

            if not new_tags and not description_needs_update and not name_needs_update and not url_needs_update:
                skipped += 1
                continue

            # Prepare new description (append to existing)
            if description_needs_update:
                if existing_desc:
                    new_description = f"{nl_description}\n\n---\n{existing_desc}"
                else:
                    new_description = nl_description
            else:
                new_description = existing_desc

            # Determine the new name (newsletter title + original name in brackets)
            if name_needs_update:
                new_name = f"{nl_title} [{link_name}]"
            else:
                new_name = link_name

            # Determine the new URL (normalized)
            new_url = normalized_url if url_needs_update else link_url

            # Log the update
            match_label = " [cyan](fuzzy match)[/cyan]" if match_type == "fuzzy" else ""
            console.print(f"  [bold]Link # {link_id:5}[/bold]{match_label}")
            if name_needs_update:
                console.print("    [cyan]name:[/cyan]")
                show_diff(link_name, new_name)
            if match_type == "fuzzy":
                console.print("    [cyan]matched url:[/cyan]")
                show_diff(link_url, nl_link)
            if url_needs_update:
                console.print("    [cyan]url:[/cyan]")
                show_diff(link_url, new_url)
            if new_tags:
                console.print("    [cyan]tags:[/cyan]")
                for tag in new_tags:
                    console.print(f"      [green]+ {tag}[/green]")
            if description_needs_update:
                desc_preview = nl_description[:80] + "..." if len(nl_description) > 80 else nl_description
                console.print("    [cyan]description:[/cyan]")
                console.print(f"      [green]+ \"{desc_preview}\"[/green]")
            console.print()

            # Perform update
            try:
                update_link(
                    base_url,
                    lw_link,
                    new_name,
                    new_url,
                    new_description,
                    tags_to_add,
                    token,
                    dry_run=dry_run,
                )
                updated += 1
            except Exception as e:
                console.print(f"    [red]Error updating: {e}[/red]")

            # Check limit
            if limit > 0 and updated >= limit:
                console.print(f"  Reached limit of {limit} updates, stopping.")
                break

        # Summary
        console.print(f"\n[bold]{'[DRY RUN] ' if dry_run else ''}Summary:[/bold]")
        console.print(f"  [green]Updated: {updated}[/green]")
        console.print(f"  [yellow]Skipped (already synced): {skipped}[/yellow]")

    # Print unmatched URLs
    if unmatched_urls:
        console.print(f"\n[bold]Unmatched Linkwarden URLs ({len(unmatched_urls)}):[/bold]")
        for url in unmatched_urls:
            console.print(f"  [yellow]{url}[/yellow]")


def main():
    parser = argparse.ArgumentParser(
        description="Linkwarden tools: sync newsletter descriptions and remove duplicates"
    )
    subparsers = parser.add_subparsers(dest="command")

    # sync command (existing functionality)
    sync_parser = subparsers.add_parser("sync", help="Sync newsletter descriptions to Linkwarden")
    sync_parser.add_argument(
        "--collection",
        type=int,
        default=None,
        help="Linkwarden collection ID (default: all collections)",
    )
    sync_parser.add_argument(
        "--jsonl",
        type=str,
        default="data/newsletters.jsonl",
        help="Path to newsletters.jsonl (default: data/newsletters.jsonl)",
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without updating Linkwarden",
    )
    sync_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of links to update (0 = no limit)",
    )

    # list command
    list_parser = subparsers.add_parser("list", help="List all links grouped by collection")
    list_parser.add_argument(
        "--collection",
        type=int,
        default=None,
        help="Filter to specific collection ID",
    )

    # remove-duplicates command
    dup_parser = subparsers.add_parser("remove-duplicates", help="Find and remove duplicate links across all collections")
    dup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview deletions without actually deleting",
    )

    # For backward compatibility, also add sync args to main parser
    parser.add_argument(
        "--collection",
        type=int,
        default=None,
        help="Linkwarden collection ID (default: all collections)",
    )
    parser.add_argument(
        "--jsonl",
        type=str,
        default="data/newsletters.jsonl",
        help="Path to newsletters.jsonl (default: data/newsletters.jsonl)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without updating Linkwarden",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of links to update (0 = no limit)",
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    base_url = os.environ.get("LINKWARDEN_URL", "https://links.kusmierz.be")
    token = os.environ.get("LINKWARDEN_TOKEN")
    if not token:
        console.print("[red]Error: LINKWARDEN_TOKEN not set in environment[/red]")
        sys.exit(1)

    # Default to sync for backward compatibility (when no subcommand given)
    if args.command is None or args.command == "sync":
        sync_links(
            base_url=base_url,
            jsonl_path=args.jsonl,
            token=token,
            collection_id=args.collection,
            dry_run=args.dry_run,
            limit=args.limit,
        )
    elif args.command == "list":
        list_links(base_url, token, collection_id=args.collection)
    elif args.command == "remove-duplicates":
        remove_duplicates(base_url, token, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
