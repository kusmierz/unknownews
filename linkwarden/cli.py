"""CLI argument parsing and dispatch for linkwarden tools."""

import argparse
import sys

from common.display import console
from .api import set_verbose
from .commands import add_link, enrich_all_links, list_links, remove_duplicates


def _add_add_parser(subparsers):
    """Add the 'add' subcommand parser."""
    p = subparsers.add_parser("add", help="Add a URL to Linkwarden with enrichment")
    p.add_argument("url", type=str, help="URL to add")
    p.add_argument("--collection", type=int, default=1, help="Target collection ID (default: 1 = Uncategorized)")
    p.add_argument("--dry-run", action="store_true", help="Preview without adding to Linkwarden")
    p.add_argument("--unread", action="store_true", help='Add "unread" tag')
    p.add_argument("--silent", action="store_true", help="No output, just exit code (ignored with --dry-run)")
    p.add_argument("-v", "--verbose", action="count", default=0, help="-v for details, -vv for LLM prompts")


def _add_list_parser(subparsers):
    """Add the 'list' subcommand parser."""
    p = subparsers.add_parser("list", help="List all links grouped by collection")
    p.add_argument("--collection", type=int, default=None, help="Filter to specific collection ID")
    p.add_argument("-v", "--verbose", action="count", default=0, help="-v for URLs and descriptions, -vv for full details")


def _add_remove_duplicates_parser(subparsers):
    """Add the 'remove-duplicates' subcommand parser."""
    p = subparsers.add_parser("remove-duplicates", help="Find and remove duplicate links across all collections")
    p.add_argument("--dry-run", action="store_true", help="Preview deletions without actually deleting")
    p.add_argument("-v", "--verbose", action="count", default=0, help="-v for details, -vv for full metadata")


def _add_enrich_all_parser(subparsers):
    """Add the 'enrich-all' subcommand parser."""
    p = subparsers.add_parser("enrich-all", help="Enrich links (newsletter data + LLM)")
    p.add_argument("--collection", type=int, default=None, help="Filter to specific collection ID")
    p.add_argument("--dry-run", action="store_true", help="Preview changes without updating Linkwarden")
    p.add_argument("--force", action="store_true", help="Overwrite all LLM fields, not just empty ones")
    p.add_argument("--limit", type=int, default=0, help="Limit number of links to process (0 = no limit)")
    p.add_argument("--show-unmatched", action="store_true", help="Show URLs not found in newsletter index")
    p.add_argument("-v", "--verbose", action="count", default=0, help="-v for details, -vv for LLM prompts")
    source_group = p.add_mutually_exclusive_group()
    source_group.add_argument("--newsletter-only", action="store_true", help="Only use newsletter data (no LLM)")
    source_group.add_argument("--llm-only", action="store_true", help="Only use LLM (no newsletter matching)")


def build_parser() -> argparse.ArgumentParser:
    """Build and return the main argument parser."""
    parser = argparse.ArgumentParser(
        description="Linkwarden tools: enrich links, manage duplicates, and more"
    )
    subparsers = parser.add_subparsers(dest="command")

    _add_add_parser(subparsers)
    _add_list_parser(subparsers)
    _add_remove_duplicates_parser(subparsers)
    _add_enrich_all_parser(subparsers)

    return parser


def dispatch(args) -> int:
    """Route parsed args to the appropriate command function.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    if getattr(args, "verbose", 0):
        set_verbose(True)

    if args.command not in ("add",) or (args.command == "add" and args.silent):
        console.print(f"[bold]linkwarden[/bold] {args.command}\n")

    if args.command == "add":
        return add_link(
            url=args.url,
            collection_id=args.collection,
            dry_run=args.dry_run,
            unread=args.unread,
            silent=args.silent,
            verbose=args.verbose,
        )
    elif args.command == "list":
        list_links(collection_id=args.collection, verbose=args.verbose)
        return 0
    elif args.command == "remove-duplicates":
        remove_duplicates(dry_run=args.dry_run, verbose=args.verbose)
        return 0
    elif args.command == "enrich-all":
        enrich_all_links(
            collection_id=args.collection,
            dry_run=args.dry_run,
            force=args.force,
            limit=args.limit,
            verbose=args.verbose,
            newsletter_only=args.newsletter_only,
            llm_only=args.llm_only,
            show_unmatched=args.show_unmatched,
        )
        return 0
    return 1


def main():
    """Entry point for the linkwarden CLI."""
    from dotenv import load_dotenv
    load_dotenv()

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    exit_code = dispatch(args)
    sys.exit(exit_code)
