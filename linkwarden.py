#!/usr/bin/env python3
"""
Linkwarden tools: sync newsletter descriptions and remove duplicate links.

Usage:
    # List all links grouped by collection
    python linkwarden.py list                    # list all links
    python linkwarden.py list --collection 14   # list links from specific collection

    # Sync newsletter descriptions to Linkwarden (all collections by default)
    python linkwarden.py sync                    # sync all collections
    python linkwarden.py sync --collection 14    # sync specific collection
    python linkwarden.py sync --dry-run          # preview without updating

    # Remove duplicates across all collections (keeps oldest link in each group)
    python linkwarden.py remove-duplicates --dry-run  # preview deletions
    python linkwarden.py remove-duplicates            # actually delete duplicates

    # Backward compatibility (defaults to sync)
    python linkwarden.py --dry-run               # same as: sync --dry-run
"""

import argparse
import os
import sys

from dotenv import load_dotenv

# Import from linkwarden modules
from linkwarden.display import console
from linkwarden.commands import list_links, remove_duplicates, sync_links


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
