#!/usr/bin/env python3
"""
Linkwarden tools: enrich links, manage duplicates, and more.

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

    # Enrich links (newsletter data + LLM)
    python linkwarden.py enrich                       # newsletter match + LLM (default)
    python linkwarden.py enrich --newsletter-only     # newsletter data only
    python linkwarden.py enrich --llm-only            # LLM only
    python linkwarden.py enrich --collection 14       # specific collection
    python linkwarden.py enrich --force               # overwrite all LLM fields
    python linkwarden.py enrich --dry-run             # preview without updating
    python linkwarden.py enrich --limit 5             # limit processed links
    python linkwarden.py enrich --show-unmatched      # show URLs not in newsletter

    # Remove duplicates across all collections (keeps oldest link in each group)
    python linkwarden.py remove-duplicates --dry-run  # preview deletions
    python linkwarden.py remove-duplicates            # actually delete duplicates
"""

import argparse
import sys

from dotenv import load_dotenv

# Import from linkwarden modules
from linkwarden.display import console
from linkwarden.api import set_verbose
from linkwarden.commands import add_link, enrich_links, fetch_url, list_links, remove_duplicates


def main():
    parser = argparse.ArgumentParser(
        description="Linkwarden tools: enrich links, manage duplicates, and more"
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
    add_parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="-v for details, -vv for LLM prompts",
    )

    # list command
    list_parser = subparsers.add_parser("list", help="List all links grouped by collection")
    list_parser.add_argument(
        "--collection",
        type=int,
        default=None,
        help="Filter to specific collection ID",
    )
    list_parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="-v for URLs and descriptions, -vv for full details",
    )

    # remove-duplicates command
    dup_parser = subparsers.add_parser("remove-duplicates", help="Find and remove duplicate links across all collections")
    dup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview deletions without actually deleting",
    )
    dup_parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="-v for details, -vv for full metadata",
    )

    # fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch and display content for a URL")
    fetch_parser.add_argument(
        "url",
        type=str,
        help="URL to fetch",
    )
    fetch_parser.add_argument(
        "--raw",
        action="store_true",
        help="Show raw text content only",
    )
    fetch_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Bypass cache and re-fetch",
    )
    fetch_parser.add_argument(
        "--enrich",
        action="store_true",
        help="Show enrichment data from cache",
    )
    fetch_parser.add_argument(
        "--summary",
        action="store_true",
        help="Generate LLM summary",
    )
    fetch_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    fetch_parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="-v for fetch details",
    )

    # enrich command
    enrich_parser = subparsers.add_parser("enrich", help="Enrich links (newsletter data + LLM)")
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
        help="Overwrite all LLM fields, not just empty ones",
    )
    enrich_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of links to process (0 = no limit)",
    )
    enrich_parser.add_argument(
        "--show-unmatched",
        action="store_true",
        help="Show URLs not found in newsletter index",
    )
    enrich_parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="-v for details, -vv for LLM prompts",
    )
    # Mutually exclusive: --newsletter-only vs --llm-only
    source_group = enrich_parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--newsletter-only",
        action="store_true",
        help="Only use newsletter data (no LLM)",
    )
    source_group.add_argument(
        "--llm-only",
        action="store_true",
        help="Only use LLM (no newsletter matching)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load environment variables (commands will read LINKWARDEN_URL and LINKWARDEN_TOKEN)
    load_dotenv()

    # Enable verbose API logging if requested
    if getattr(args, "verbose", 0):
        set_verbose(True)

    # add/fetch commands handle their own header
    if args.command not in ("add", "fetch") or (args.command == "add" and args.silent):
        console.print(f"[bold]linkwarden[/bold] {args.command}\n")

    if args.command == "fetch":
        exit_code = fetch_url(
            url=args.url,
            verbose=args.verbose,
            raw=args.raw,
            force=args.force,
            enrich=args.enrich,
            summary=args.summary,
            json_output=args.json_output,
        )
        sys.exit(exit_code)
    elif args.command == "add":
        exit_code = add_link(
            url=args.url,
            collection_id=args.collection,
            dry_run=args.dry_run,
            unread=args.unread,
            silent=args.silent,
            verbose=args.verbose,
        )
        sys.exit(exit_code)
    elif args.command == "list":
        list_links(collection_id=args.collection, verbose=args.verbose)
    elif args.command == "remove-duplicates":
        remove_duplicates(dry_run=args.dry_run, verbose=args.verbose)
    elif args.command == "enrich":
        enrich_links(
            collection_id=args.collection,
            dry_run=args.dry_run,
            force=args.force,
            limit=args.limit,
            verbose=args.verbose,
            newsletter_only=args.newsletter_only,
            llm_only=args.llm_only,
            show_unmatched=args.show_unmatched,
        )


if __name__ == "__main__":
    main()
