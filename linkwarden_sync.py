#!/usr/bin/env python3
"""
Sync newsletter link descriptions and date tags to Linkwarden bookmarks.

Usage:
    python linkwarden_sync.py                    # use defaults
    python linkwarden_sync.py --collection 14    # specify collection
    python linkwarden_sync.py --dry-run          # preview without updating
"""

import argparse
import json
import os
import sys
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv


# ANSI color codes
class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

    @classmethod
    def disable(cls):
        cls.RED = cls.GREEN = cls.YELLOW = cls.BLUE = cls.CYAN = cls.RESET = cls.BOLD = ""


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


def get_url_path_key(url: str) -> str:
    """Extract just the domain and path for fuzzy matching (no protocol, no query, no fragment)."""
    if not url:
        return ""
    parsed = urlparse(url.strip())
    # Just netloc + path, lowercase, no trailing slash
    key = f"{parsed.netloc}{parsed.path}".lower().rstrip("/")
    return key


def normalize_url(url: str) -> str:
    """Normalize URL for matching: lowercase, strip trailing slash, handle http/https, remove fragments and tracking params."""
    if not url:
        return ""
    url = url.strip()

    # Parse URL
    parsed = urlparse(url)

    # Remove fragment (#)
    # Remove tracking query params
    tracking_params = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "ref", "source", "fbclid", "gclid", "mc_cid", "mc_eid",
    }

    if parsed.query:
        params = parsed.query.split("&")
        filtered = [p for p in params if p.split("=")[0].lower() not in tracking_params]
        new_query = "&".join(filtered)
    else:
        new_query = ""

    # Rebuild URL without fragment, with filtered query
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if new_query:
        normalized += f"?{new_query}"

    # Normalize http to https
    if normalized.startswith("http://"):
        normalized = "https://" + normalized[7:]

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
    """Fetch all links from a Linkwarden collection with pagination."""
    headers = {"Authorization": f"Bearer {token}"}
    all_links = []
    cursor = 0
    page_size = 50

    while True:
        url = f"{base_url}/api/v1/links?collectionId={collection_id}&sort=0&cursor={cursor}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        links = data.get("response", [])
        if not links:
            break

        all_links.extend(links)

        # If we got fewer links than page size, we've reached the end
        if len(links) < page_size:
            break

        cursor += len(links)

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


def sync_links(
    base_url: str,
    collection_id: int,
    jsonl_path: str,
    dry_run: bool = False,
    limit: int = 0,
) -> None:
    """Main sync logic: match URLs and update Linkwarden."""
    token = os.environ.get("LINKWARDEN_TOKEN")
    if not token:
        print("Error: LINKWARDEN_TOKEN not set in environment")
        return

    # Load newsletter index
    print(f"Loading newsletter index from {jsonl_path}...")
    newsletter_index, newsletter_fuzzy_index = load_newsletter_index(jsonl_path)
    print(f"  Indexed {len(newsletter_index)} unique links from newsletters")

    # Fetch Linkwarden links
    print(f"\nFetching links from Linkwarden collection {collection_id}...")
    linkwarden_links = fetch_collection_links(base_url, collection_id, token)
    print(f"  Fetched {len(linkwarden_links)} links from Linkwarden")

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
    print(f"\n{Colors.GREEN}Exact: {exact_count}{Colors.RESET} | {Colors.CYAN}Fuzzy: {fuzzy_count}{Colors.RESET} | {Colors.YELLOW}Unmatched: {len(unmatched_urls)}{Colors.RESET}")

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
                    new_description = f"{existing_desc}\n\n---\n\n{nl_description}"
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
            match_label = f" {Colors.CYAN}(fuzzy match){Colors.RESET}" if match_type == "fuzzy" else ""
            print(f"  {Colors.BOLD}Link ID: {link_id}{Colors.RESET}{match_label}")
            if name_needs_update:
                print(f"    {Colors.CYAN}name:{Colors.RESET}")
                print(f"      {Colors.RED}- {link_name}{Colors.RESET}")
                print(f"      {Colors.GREEN}+ {new_name}{Colors.RESET}")
            if url_needs_update or match_type == "fuzzy":
                print(f"    {Colors.CYAN}url:{Colors.RESET}")
                print(f"      {Colors.RED}- {link_url}{Colors.RESET}")
                print(f"      {Colors.GREEN}+ {new_url}{Colors.RESET}")
            if new_tags:
                print(f"    {Colors.CYAN}tags:{Colors.RESET}")
                for tag in new_tags:
                    print(f"      {Colors.GREEN}+ {tag}{Colors.RESET}")
            if description_needs_update:
                desc_preview = nl_description[:80] + "..." if len(nl_description) > 80 else nl_description
                print(f"    {Colors.CYAN}description:{Colors.RESET}")
                print(f"      {Colors.GREEN}+ \"{desc_preview}\"{Colors.RESET}")
            print()

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
                print(f"    Error updating: {e}")

            # Check limit
            if limit > 0 and updated >= limit:
                print(f"  Reached limit of {limit} updates, stopping.")
                break

        # Summary
        print(f"\n{Colors.BOLD}{'[DRY RUN] ' if dry_run else ''}Summary:{Colors.RESET}")
        print(f"  {Colors.GREEN}Updated: {updated}{Colors.RESET}")
        print(f"  {Colors.YELLOW}Skipped (already synced): {skipped}{Colors.RESET}")

    # Print unmatched URLs
    if unmatched_urls:
        print(f"\n{Colors.BOLD}Unmatched Linkwarden URLs ({len(unmatched_urls)}):{Colors.RESET}")
        for url in unmatched_urls:
            print(f"  {Colors.YELLOW}{url}{Colors.RESET}")


def main():
    parser = argparse.ArgumentParser(
        description="Sync newsletter link descriptions to Linkwarden"
    )
    parser.add_argument(
        "--collection",
        type=int,
        default=14,
        help="Linkwarden collection ID (default: 14)",
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

    sync_links(
        base_url=base_url,
        collection_id=args.collection,
        jsonl_path=args.jsonl,
        dry_run=args.dry_run,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
