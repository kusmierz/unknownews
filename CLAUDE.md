# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Python scraper and crawler for unknownews newsletter (mrugalski.pl). Extracts structured JSON from newsletter HTML pages with automatic crawling of previous issues.

## Commands

```bash
source .venv/bin/activate        # activate virtualenv
pip install -r requirements.txt  # install deps

# Crawl newsletters (with daily caching)
python scraper.py [-n LIMIT] [-f]                 # fetch latest (default: max 10, cached daily)
python scraper.py -n 50                           # fetch up to 50 newsletters
python scraper.py --force                         # bypass daily cache
python scraper.py <url> -n 20                     # start from specific URL

# List links in Linkwarden
python linkwarden.py list                    # list all links grouped by collection
python linkwarden.py list --collection 14   # list links from specific collection

# Sync to Linkwarden
python linkwarden.py sync --dry-run          # preview changes
python linkwarden.py sync                    # sync all collections
python linkwarden.py sync --collection 14    # specify collection
python linkwarden.py sync --limit 5          # limit updates
python linkwarden.py sync --show-unmatched   # show all unmatched URLs
python linkwarden.py --dry-run               # backward compatible (no subcommand)

# Remove duplicate links across all collections
python linkwarden.py remove-duplicates --dry-run  # preview deletions
python linkwarden.py remove-duplicates            # actually delete duplicates
```

## Architecture

### scraper.py
Single-file scraper using BeautifulSoup with daily caching. Main functions:

- `scrape_newsletter(url)` -> `(newsletter_dict, previous_newsletters_list)`
- `crawl_newsletters(start_url, max_total=50, output_dir="data")` -> `int` (count)

Helper functions:
- `clean_text(text)` - removes extra spaces before punctuation
- `html_to_markdown(element)` - converts HTML to markdown (bold, italic, links, lists)
- `load_scraped_urls(output_dir)` / `save_scraped_urls(urls, output_dir)` - deduplication
- `append_newsletter(newsletter, output_dir)` - append to JSONL
- `get_latest_newsletter_url()` - fetches latest newsletter URL
- `get_premium_url(url)` - converts to premium URL using password

Caching:
- Uses `data/cache_last-fetch.txt` to track last fetch date
- Only fetches once per day (bypass with `--force`)

### linkwarden.py (main CLI)
Entry point for Linkwarden tools. Parses command-line arguments and dispatches to command implementations.

### linkwarden/ (module)
Modular Linkwarden tools for syncing newsletter descriptions and managing duplicates. Uses `rich` for colored output.

**Core modules:**
- `api.py` - Linkwarden API client
  - `fetch_all_collections(base_url, token)` - get all collections
  - `fetch_collection_links(base_url, collection_id, token)` - get links from collection (paginated)
  - `fetch_all_links(base_url, token, silent)` - get all links from all collections
  - `update_link(...)` - update link via PUT
  - `delete_link(base_url, link_id, token)` - delete link
- `url_utils.py` - URL normalization and matching
  - `normalize_url(url)` - removes fragments, tracking params, normalizes http->https
  - `get_url_path_key(url)` - extracts domain+path for fuzzy matching
  - `filter_query_params(query, keep_only)` - filters query parameters
- `newsletter.py` - Newsletter index management
  - `load_newsletter_index(jsonl_path)` -> `(exact_index, fuzzy_index)`
- `display.py` - Rich console formatting
  - `show_diff(old, new, indent, muted)` - displays inline diff
  - `get_tag_color(tag_name)` - consistent tag colors
- `duplicates.py` - Duplicate detection
  - `find_duplicates(links)` -> `(exact_groups, fuzzy_groups)`

**Commands** (in `linkwarden/commands/`):
- `list_links.py` - `list_links(base_url, token, collection_id)` - lists all links grouped by collection
- `sync.py` - `sync_links(base_url, jsonl_path, token, collection_id, dry_run, limit, show_unmatched)` - syncs descriptions
- `remove_duplicates.py` - `remove_duplicates(base_url, token, dry_run)` - finds and removes duplicates

## Output structure

```
data/
  newsletters.jsonl       # one JSON per line (scraped newsletters)
  scraped_urls.txt        # for deduplication across runs
  cache_last-fetch.txt    # daily cache timestamp (YYYY-MM-DD)
```

### Newsletter JSON schema

```json
{
  "title": "string",
  "date": "YYYY-MM-DD",
  "description": "string (markdown)",
  "sponsor": "string (markdown)",
  "links": [{"title": "string", "link": "url", "description": "string"}],
  "url": "string"
}
```

## HTML parsing notes

- Title: from `<title>` tag, strip `[#uN] 🌀 ` prefix
- Date: from `og:image` meta tag URL (e.g., `/og/20251205.png`)
- Links: in `<ol><li>` with `<strong>` for title, `<a>` for URL, `<span>` for description
- Sponsor: in `<div style="background:#eeeeee...">`, may use `<br>` or `<p>` for paragraphs
- Description: paragraphs between greeting and sponsor marker ("pora na sponsora" or "info o promocji")
- Previous newsletters: in `<ul><li>` with `<b>`/`<strong>` for date and `<a>` for link
- Use `clean_text()` after `get_text(separator=" ", strip=True)` to fix spacing around punctuation

## Environment variables

`.env` file (loaded by python-dotenv):
- `LINKWARDEN_TOKEN` - API token for Linkwarden
- `LINKWARDEN_URL` - Linkwarden instance URL (default: https://links.kusmierz.be)

## Linkwarden API

Search links (paginated):
```
GET /api/v1/search?collectionId=14&cursor=<lastId>
Response: { "data": { "links": [...], "nextCursor": 123 } }
```

Update link:
```
PUT /api/v1/links/{id}
{
  "id": 123,
  "name": "New title [Original title]",
  "url": "https://normalized.url/path",
  "description": "...",
  "collectionId": 14,
  "collection": { ... },
  "tags": [{"name": "unknow"}, {"name": "2024-12-20"}]
}
```

Get all collections:
```
GET /api/v1/collections
Response: [{ "id": 14, "name": "unknow", ... }, ...]
```

Note: `/api/v1/links` GET is deprecated, use `/api/v1/search` instead.
