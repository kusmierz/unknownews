# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Python scraper and crawler for unknownews newsletter (mrugalski.pl). Extracts structured JSON from newsletter HTML pages with automatic crawling of previous issues.

## Commands

```bash
source .venv/bin/activate        # activate virtualenv
pip install -r requirements.txt  # install deps

# Crawl newsletters
python scraper.py <url> [-n LIMIT]
python scraper.py https://mrugalski.pl/nl/wu/u8d1L2kQOHGVezsjqUWH0g -n 50

# List links in Linkwarden
python linkwarden_sync.py list                    # list all links grouped by collection
python linkwarden_sync.py list --collection 14   # list links from specific collection

# Sync to Linkwarden
python linkwarden_sync.py sync --dry-run          # preview changes
python linkwarden_sync.py sync                    # sync to collection 14
python linkwarden_sync.py sync --collection 14    # specify collection
python linkwarden_sync.py sync --limit 5          # limit updates
python linkwarden_sync.py --dry-run               # backward compatible (no subcommand)

# Remove duplicate links across all collections
python linkwarden_sync.py remove-duplicates --dry-run  # preview deletions
python linkwarden_sync.py remove-duplicates            # actually delete duplicates
```

## Architecture

### scraper.py
Single-file scraper using BeautifulSoup. Main functions:

- `scrape_newsletter(url)` -> `(newsletter_dict, previous_newsletters_list)`
- `crawl_newsletters(start_url, max_total=50, output_dir="data")` -> `int` (count)

Helper functions:
- `clean_text(text)` - removes extra spaces before punctuation
- `html_to_markdown(element)` - converts HTML to markdown (bold, italic, links, lists)
- `load_scraped_urls(output_dir)` / `save_scraped_urls(urls, output_dir)` - deduplication
- `append_newsletter(newsletter, output_dir)` - append to JSONL

### linkwarden_sync.py
Linkwarden tools: syncs newsletter descriptions and finds duplicate links. Uses `rich` for colored output.

Main functions:
- `load_newsletter_index(jsonl_path)` -> `(exact_index, fuzzy_index)` - builds two indexes for matching
- `fetch_collection_links(base_url, collection_id, token)` -> `list[dict]` - uses `/api/v1/search` with pagination
- `fetch_all_collections(base_url, token)` -> `list[dict]` - fetches all collections from Linkwarden
- `fetch_all_links(base_url, token)` -> `list[dict]` - fetches all links from all collections
- `list_links(base_url, token, collection_id)` - lists all links grouped by collection with clickable names
- `find_duplicates(links)` -> `(exact_groups, fuzzy_groups)` - finds duplicates using normalized URL and fuzzy matching
- `remove_duplicates(base_url, token, dry_run)` - finds and removes duplicate links
- `update_link(base_url, link, new_name, new_url, new_description, new_tags, token)` -> `bool` - PUT to update
- `sync_links(base_url, collection_id, jsonl_path, dry_run, limit)` - main sync logic

Helpers:
- `normalize_url(url)` - removes fragments, tracking params (utm_*, fbclid, etc.), normalizes http->https
- `get_url_path_key(url)` - extracts domain+path for fuzzy matching
- `show_diff(old, new)` - displays inline diff with highlighted changes
- `display_duplicates(exact_groups, fuzzy_groups, total_links)` - displays duplicate report

## Output structure

```
data/
  newsletters.jsonl    # one JSON per line
  scraped_urls.txt     # for deduplication across runs
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
