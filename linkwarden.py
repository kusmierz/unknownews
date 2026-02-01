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
import os
import shutil
import sys

from dotenv import load_dotenv
from rich.markup import escape
from rich.text import Text

# Import from linkwarden modules
from linkwarden.api import (
    fetch_all_collections,
    fetch_collection_links,
    fetch_all_links,
    update_link,
    delete_link,
)
from linkwarden.url_utils import normalize_url, get_url_path_key
from linkwarden.newsletter import load_newsletter_index
from linkwarden.display import console, get_tag_color, show_diff
from linkwarden.duplicates import find_duplicates


# Command implementations

def list_links(base_url: str, token: str, collection_id: int | None = None) -> None:
    """List all links grouped by collection."""
    # Fetch links
    with console.status("Fetching...", spinner="dots"):
        if collection_id is not None:
            links = fetch_collection_links(base_url, collection_id, token)
            collections = fetch_all_collections(base_url, token)
            collection_name = next(
                (c.get("name", f"Collection {collection_id}") for c in collections if c["id"] == collection_id),
                f"Collection {collection_id}"
            )
            for link in links:
                link["_collection_name"] = collection_name
        else:
            links = fetch_all_links(base_url, token, silent=True)

    if not links:
        console.print("[dim]No links found.[/dim]")
        return

    # Group links by collection
    by_collection = defaultdict(list)
    for link in links:
        by_collection[link.get("_collection_name", "Unknown")].append(link)

    # Calculate widths
    terminal_width = shutil.get_terminal_size().columns or 120
    name_max = min(70, terminal_width - 25)
    desc_max = terminal_width - 12

    # Display links
    for coll_name, coll_links in sorted(by_collection.items()):
        coll_id = coll_links[0].get("collectionId", collection_id)
        coll_url = f"{base_url}/collections/{coll_id}"
        console.print(f"\n[bold][link={coll_url}]{escape(coll_name)}[/link][/bold] [dim]({len(coll_links)})[/dim]")

        for link in sorted(coll_links, key=lambda x: x.get("id", 0)):
            link_id = link.get("id", "?")
            name = (link.get("name") or "").strip() or "Untitled"
            if name == "Just a moment...":
                name = "Untitled"
            desc = (link.get("description") or "").replace("\n", " ").strip()
            tags = [t.get("name", "") for t in link.get("tags", []) if t.get("name")]
            link_url = f"{base_url}/preserved/{link_id}?format=4"

            if len(name) > name_max:
                name = name[:name_max - 3] + "..."
            if len(desc) > desc_max:
                desc = desc[:desc_max - 3] + "..."

            # Name line with tags
            line = Text()
            line.append(f"  #{link_id:<5} ", style="dim")
            line.append(name, style=f"link {link_url}")
            if tags:
                line.append("  ")
                for tag in tags:
                    line.append(f"[{tag}] ", style=f"dim {get_tag_color(tag)}")
            console.print(line)

            if desc:
                console.print(f"            [dim]{desc}[/dim]")

    # Summary
    console.print(f"\n[bold]{len(links)}[/bold] links total")

    # Duplicates hint
    exact_groups, fuzzy_groups = find_duplicates(links)
    total_dups = sum(len(g["links"]) - 1 for g in exact_groups + fuzzy_groups)
    if total_dups > 0:
        console.print(f"[yellow]{total_dups} duplicates[/yellow] [dim]- run `remove-duplicates` to clean up[/dim]")


def remove_duplicates(base_url: str, token: str, dry_run: bool = False) -> None:
    """Fetch all links across all collections, find duplicates, and remove them."""
    dry_label = "[dim](dry-run)[/dim] " if dry_run else ""

    with console.status("Fetching...", spinner="dots"):
        all_links = fetch_all_links(base_url, token, silent=True)

    exact_groups, fuzzy_groups = find_duplicates(all_links)
    total_to_delete = sum(len(g["links"]) - 1 for g in exact_groups + fuzzy_groups)

    console.print(f"[bold]{len(all_links)}[/bold] links, [red]{len(exact_groups)}[/red] exact + [yellow]{len(fuzzy_groups)}[/yellow] fuzzy duplicate groups\n")

    if not exact_groups and not fuzzy_groups:
        console.print("[green]No duplicates found.[/green]")
        return

    # Show duplicate groups with details
    all_groups = [("exact", g) for g in exact_groups] + [("fuzzy", g) for g in fuzzy_groups]

    for match_type, group in all_groups:
        links = sorted(group["links"], key=lambda x: x.get("id", 0))
        key = group.get("normalized_url") or group.get("path_key", "")
        emoji = "🎯" if match_type == "exact" else "🔍"

        console.print(f"{emoji} [blue][link={key}]{key[:70]}[/link][/blue]")

        first_url = links[0].get("url", "")
        for i, link in enumerate(links):
            link_id = link.get("id", "?")
            name = link.get("name", "Untitled")[:55]
            coll = link.get("_collection_name", "?")
            link_url = link.get("url", "")
            ui_url = f"{base_url}/preserved/{link_id}?format=4"

            if i == 0:
                console.print(f"  [green]keep[/green]   #{link_id:<5} [link={ui_url}]{name}[/link] [dim][{coll}][/dim]")
            else:
                console.print(f"  [red]delete[/red] #{link_id:<5} [link={ui_url}]{name}[/link] [dim][{coll}][/dim]")
                if link_url != first_url:
                    show_diff(first_url, link_url, indent="         ", muted=True)
        console.print()

    # Confirm and delete
    links_to_delete = []
    for group in exact_groups + fuzzy_groups:
        sorted_links = sorted(group["links"], key=lambda x: x.get("id", 0))
        links_to_delete.extend(sorted_links[1:])

    if not dry_run:
        deleted = 0
        errors = 0
        with console.status("Deleting...", spinner="dots"):
            for link in links_to_delete:
                try:
                    delete_link(base_url, link.get("id"), token)
                    deleted += 1
                except Exception:
                    errors += 1
        console.print(f"[red]{deleted} deleted[/red]" + (f", [red]{errors} errors[/red]" if errors else ""))
    else:
        console.print(f"{dry_label}[red]{total_to_delete}[/red] would be deleted")


def sync_links(
    base_url: str,
    jsonl_path: str,
    token: str,
    collection_id: int | None = None,
    dry_run: bool = False,
    limit: int = 0,
    show_unmatched: bool = False,
) -> None:
    """Main sync logic: match URLs and update Linkwarden.

    If collection_id is None, syncs all collections.
    """
    # Show scope
    if collection_id is not None:
        collections = fetch_all_collections(base_url, token)
        coll_name = next((c.get("name") for c in collections if c["id"] == collection_id), f"#{collection_id}")
        coll_url = f"{base_url}/collections/{collection_id}"
        console.print(f"Collection: [bold][link={coll_url}]{coll_name}[/link][/bold]\n")
    else:
        console.print("[dim]All collections[/dim]\n")

    # Load newsletter index
    with console.status("Loading index...", spinner="dots"):
        newsletter_index, newsletter_fuzzy_index = load_newsletter_index(jsonl_path)

    # Fetch Linkwarden links
    with console.status("Fetching links...", spinner="dots"):
        if collection_id is not None:
            linkwarden_links = fetch_collection_links(base_url, collection_id, token)
        else:
            linkwarden_links = fetch_all_links(base_url, token, silent=True)

    console.print(f"[bold]{len(linkwarden_links)}[/bold] links, [bold]{len(newsletter_index)}[/bold] indexed")

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
    console.print(f"Matched: [green]{exact_count}[/green] exact, [cyan]{fuzzy_count}[/cyan] fuzzy, [dim]{len(unmatched_urls)} unmatched[/dim]\n")

    if not matches:
        console.print("[dim]Nothing to update.[/dim]")
        return

    # Process updates
    updated = 0
    skipped = 0
    dry_label = "[dim](dry-run)[/dim] " if dry_run else ""

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
        name_needs_update = (
            nl_title
            and link_name
            and link_name != nl_title
            and not link_name.startswith(nl_title)
        )
        url_needs_update = normalized_url and normalized_url != link_url

        if not new_tags and not description_needs_update and not name_needs_update and not url_needs_update:
            skipped += 1
            continue

        # Prepare updates
        if description_needs_update:
            new_description = f"{nl_description}\n\n---\n{existing_desc}" if existing_desc else nl_description
        else:
            new_description = existing_desc

        new_name = f"{nl_title} [{link_name}]" if name_needs_update else link_name
        new_url = normalized_url if url_needs_update else link_url

        # Show update
        fuzzy_label = " [cyan]~[/cyan]" if match_type == "fuzzy" else ""
        console.print(f"{dry_label}[green]+[/green] #{link_id}{fuzzy_label}  [bold]{link_name[:50]}[/bold]")

        if name_needs_update:
            show_diff(link_name, new_name, indent="    ")
        if url_needs_update:
            show_diff(link_url, new_url, indent="    ")
        if new_tags:
            console.print(f"    [green]+ tags: {', '.join(new_tags)}[/green]")
        extra_tags = existing_tags - set(tags_to_add) - {"unknow"}
        if extra_tags:
            console.print(f"    [dim]  tags: {', '.join(sorted(extra_tags))}[/dim]")
        if description_needs_update:
            if existing_desc:
                old_desc = existing_desc[:60] + "..." if len(existing_desc) > 60 else existing_desc
                new_desc = nl_description[:60] + "..." if len(nl_description) > 60 else nl_description
                show_diff(old_desc, new_desc, indent="    ")
            else:
                desc_preview = nl_description[:60] + "..." if len(nl_description) > 60 else nl_description
                console.print(f"    [green]+ desc: {desc_preview}[/green]")

        # Perform update
        try:
            update_link(base_url, lw_link, new_name, new_url, new_description, tags_to_add, token, dry_run=dry_run)
            updated += 1
        except Exception as e:
            console.print(f"    [red]! {e}[/red]")

        if limit > 0 and updated >= limit:
            console.print(f"\n[dim]Limit of {limit} reached.[/dim]")
            break

    # Summary
    console.print(f"\n{dry_label}[green]{updated} updated[/green], [dim]{skipped} skipped[/dim]")

    if unmatched_urls:
        if show_unmatched:
            console.print(f"\n[dim]Unmatched ({len(unmatched_urls)}):[/dim]")
            for url in unmatched_urls:
                console.print(f"  [dim]{url}[/dim]")
        else:
            console.print(f"\n[dim]{len(unmatched_urls)} unmatched (use --show-unmatched to list)[/dim]")


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
    sync_parser.add_argument(
        "--show-unmatched",
        action="store_true",
        help="Show all unmatched Linkwarden URLs",
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
    parser.add_argument(
        "--show-unmatched",
        action="store_true",
        help="Show all unmatched Linkwarden URLs",
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    base_url = os.environ.get("LINKWARDEN_URL", "https://links.kusmierz.be")
    token = os.environ.get("LINKWARDEN_TOKEN")
    if not token:
        console.print("[red]Error: LINKWARDEN_TOKEN not set in environment[/red]")
        sys.exit(1)

    command = args.command or "sync"
    console.print(f"[bold]linkwarden[/bold] {command}\n")

    if command == "sync":
        sync_links(
            base_url=base_url,
            jsonl_path=args.jsonl,
            token=token,
            collection_id=args.collection,
            dry_run=args.dry_run,
            limit=args.limit,
            show_unmatched=args.show_unmatched,
        )
    elif command == "list":
        list_links(base_url, token, collection_id=args.collection)
    elif command == "remove-duplicates":
        remove_duplicates(base_url, token, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
