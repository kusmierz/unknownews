#!/usr/bin/env python3
"""
Linkwarden tools: enrich links, manage duplicates, and more.

Usage:
    python linkwarden.py add <url>                    # add to Uncategorized (with warning)
    python linkwarden.py add <url> --dry-run          # preview without adding
    python linkwarden.py add <url> --collection 14    # specify target collection
    python linkwarden.py add <url> --unread           # add with "unread" tag
    python linkwarden.py add <url> --silent           # no output, just exit code

    python linkwarden.py list                         # list all links
    python linkwarden.py list --collection 14         # list links from specific collection

    python linkwarden.py enrich-all                   # newsletter match + LLM (default)
    python linkwarden.py enrich-all --newsletter-only # newsletter data only
    python linkwarden.py enrich-all --llm-only        # LLM only
    python linkwarden.py enrich-all --collection 14   # specific collection
    python linkwarden.py enrich-all --force           # overwrite all LLM fields
    python linkwarden.py enrich-all --dry-run         # preview without updating
    python linkwarden.py enrich-all --limit 5         # limit processed links

    python linkwarden.py remove-duplicates --dry-run  # preview deletions
    python linkwarden.py remove-duplicates            # actually delete duplicates
"""

from linkwarden.cli import main

if __name__ == "__main__":
    main()
