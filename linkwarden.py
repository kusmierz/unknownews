#!/usr/bin/env python3
"""
Linkwarden tools: sync newsletter descriptions, enrich links, and remove duplicates.

Usage:
    # Add a URL to Linkwarden with enrichment
    python linkwarden.py add <url>                    # add to Uncategorized (with warning)
    python linkwarden.py add <url> --dry-run          # preview without adding
    python linkwarden.py add <url> --collection 14    # specify target collection
    python linkwarden.py add <url> --unread           # add with "unread" tag
    python linkwarden.py add <url> --silent           # no output, just exit code

    # List all links grouped by collection
    python linkwarden.py list                    # list all links
    python linkwarden.py list --collection 14   # list links from specific collection

    # Sync newsletter descriptions to Linkwarden (all collections by default)
    python linkwarden.py sync                    # sync all collections
    python linkwarden.py sync --collection 14    # sync specific collection
    python linkwarden.py sync --dry-run          # preview without updating

    # Enrich links using LLM (generate titles, descriptions, tags)
    python linkwarden.py enrich                    # enrich all links (empty fields only)
    python linkwarden.py enrich --collection 14    # specific collection
    python linkwarden.py enrich --force            # overwrite all fields
    python linkwarden.py enrich --dry-run          # preview without updating
    python linkwarden.py enrich --limit 5          # limit number of links

    # Remove duplicates across all collections (keeps oldest link in each group)
    python linkwarden.py remove-duplicates --dry-run  # preview deletions
    python linkwarden.py remove-duplicates            # actually delete duplicates
"""

import argparse
import sys

from dotenv import load_dotenv

# Import from linkwarden modules
from linkwarden.display import console
from linkwarden.commands import add_link, enrich_links, list_links, remove_duplicates, sync_links


def main():
    parser = argparse.ArgumentParser(
        description="Linkwarden tools: sync newsletter descriptions and remove duplicates"
    )
    subparsers = parser.add_subparsers(dest="command")

    # add command
    add_parser = subparsers.add_parser("add", help="Add a URL to Linkwarden with enrichment")
    add_parser.add_argument(
        "url",
        type=str,
        help="URL to add",
    )
    add_parser.add_argument(
        "--collection",
        type=int,
        default=1,
        help="Target collection ID (default: 1 = Uncategorized)",
    )
    add_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without adding to Linkwarden",
    )
    add_parser.add_argument(
        "--unread",
        action="store_true",
        help='Add "unread" tag',
    )
    add_parser.add_argument(
        "--silent",
        action="store_true",
        help="No output, just exit code (ignored with --dry-run)",
    )

    # sync command (existing functionality)
    sync_parser = subparsers.add_parser("sync", help="Sync newsletter descriptions to Linkwarden")
    sync_parser.add_argument(
        "--collection",
        type=int,
        default=None,
        help="Linkwarden collection ID (default: all collections)",
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

    # enrich command
    enrich_parser = subparsers.add_parser("enrich", help="Enrich links using LLM (titles, descriptions, tags)")
    enrich_parser.add_argument(
        "--collection",
        type=int,
        default=None,
        help="Filter to specific collection ID",
    )
    enrich_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without updating Linkwarden",
    )
    enrich_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite all fields, not just empty ones",
    )
    enrich_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of links to process (0 = no limit)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load environment variables (commands will read LINKWARDEN_URL and LINKWARDEN_TOKEN)
    load_dotenv()

    # add command handles its own header
    if args.command != "add" or args.silent:
        if args.command != "add":
            console.print(f"[bold]linkwarden[/bold] {args.command}\n")

    if args.command == "add":
        exit_code = add_link(
            url=args.url,
            collection_id=args.collection,
            dry_run=args.dry_run,
            unread=args.unread,
            silent=args.silent,
        )
        sys.exit(exit_code)
    elif args.command == "sync":
        sync_links(
            collection_id=args.collection,
            dry_run=args.dry_run,
            limit=args.limit,
            show_unmatched=args.show_unmatched,
        )
    elif args.command == "list":
        list_links(collection_id=args.collection)
    elif args.command == "remove-duplicates":
        remove_duplicates(dry_run=args.dry_run)
    elif args.command == "enrich":
        enrich_links(
            collection_id=args.collection,
            dry_run=args.dry_run,
            force=args.force,
            limit=args.limit,
        )


if __name__ == "__main__":
    main()
