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

# Add URL to Linkwarden (with newsletter or LLM enrichment)
python linkwarden.py add <url>                    # add to Uncategorized (with warning)
python linkwarden.py add <url> --dry-run          # preview without adding
python linkwarden.py add <url> --collection 14    # specify target collection
python linkwarden.py add <url> --unread           # add with "unread" tag
python linkwarden.py add <url> --silent           # no output, just exit code

# List links in Linkwarden
python linkwarden.py list                    # list all links grouped by collection
python linkwarden.py list --collection 14   # list links from specific collection

# Sync to Linkwarden
python linkwarden.py sync --dry-run          # preview changes
python linkwarden.py sync                    # sync all collections
python linkwarden.py sync --collection 14    # specify collection
python linkwarden.py sync --limit 5          # limit updates
python linkwarden.py sync --show-unmatched   # show all unmatched URLs

# Remove duplicate links across all collections
python linkwarden.py remove-duplicates --dry-run  # preview deletions
python linkwarden.py remove-duplicates            # actually delete duplicates

# Enrich links with LLM-generated titles, descriptions, and tags
python linkwarden.py enrich --dry-run             # preview (caches LLM results)
python linkwarden.py enrich                       # enrich empty fields only
python linkwarden.py enrich --collection 14       # specific collection
python linkwarden.py enrich --force               # regenerate all fields
python linkwarden.py enrich --limit 5             # limit processed (including failures)
python linkwarden.py enrich --verbose             # show detailed LLM request information
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
- Uses `data/last-fetch_cache.txt` to track last fetch date
- Only fetches once per day (bypass with `--force`)

### linkwarden.py (main CLI)
Entry point for Linkwarden tools. Parses command-line arguments and dispatches to command implementations.

### linkwarden/ (module)
Modular Linkwarden tools for syncing newsletter descriptions and managing duplicates. Uses `rich` for colored output.

**Core modules:**
- `config.py` - Configuration utility
  - `get_api_config()` - reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment
- `cache.py` - Unified cache service for all cache types
  - `get_cache(key, cache_type, max_age_days)` - get cached value with optional expiration
  - `set_cache(key, value, cache_type, ttl_days)` - set cache with optional TTL
  - `remove_cache(key, cache_type)` - remove specific cache entry
  - `clear_cache_type(cache_type)` - clear all cache for a type
- `api.py` - Linkwarden API client (self-sustainable, reads credentials from environment)
  - `fetch_all_collections()` - get all collections
  - `fetch_collection_links(collection_id)` - get links from collection (paginated)
  - `update_link(link, new_name, new_url, new_description, new_tags, dry_run)` - update link via PUT
  - `create_link(url, name, description, tags, collection_id)` - create link via POST
  - `delete_link(link_id)` - delete link
- `links.py` - Link operations facade (re-exports API functions + orchestration)
  - `fetch_all_links(silent)` - get all links from all collections (uses collections cache)
  - Re-exports: `fetch_collection_links`, `update_link`, `create_link`, `delete_link`
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
- `content_fetcher.py` - Content fetching for articles and videos
  - `fetch_content(url)` - orchestrates content fetching based on URL type
  - `fetch_article_content(url)` - uses trafilatura to extract article content
  - `fetch_video_content(url)` - uses yt-dlp for metadata + youtube-transcript-api for transcripts (cached 7 days)
  - `extract_transcript_from_info(info_dict)` - extracts transcript via youtube-transcript-api (languages: original → en → pl)
  - Exceptions: `RateLimitError` (YouTube request blocked / IP blocked)
  - **Optimization**: Caches only essential data + transcript (~10 KB per video)
    - Excludes heavy unused data: formats, thumbnails, heatmap, subtitles
    - Preserves: metadata, chapters, stats, categories, extracted transcript
    - Caches extracted transcript to avoid re-fetching on every run
    - Handles rate limits gracefully (continues without transcript instead of crashing)
- `llm.py` - LLM API client (OpenAI-compatible)
  - `enrich_link(url, prompt_path)` - calls LLM to generate title, description, tags
  - `format_content_for_llm(content_data)` - formats content with chapters (videos) or article text for LLM
  - `call_responses_api(...)` - OpenAI Responses API with web search
  - `call_chat_completions_api(...)` - standard Chat Completions API
  - `parse_json_response(text)` - parses JSON from LLM response, decodes HTML entities
- `llm_cache.py` - Thin wrapper around unified cache for LLM results (no expiry)
  - `get_cached(url)` / `set_cached(url, result)` / `remove_cached(url)`
- `yt_dlp_cache.py` - Thin wrapper around unified cache for yt-dlp video info (7-day TTL)
  - `get_cached(url)` / `set_cached(url, info_dict)`
- `collections_cache.py` - Thin wrapper around unified cache for collections (1-day TTL)
  - `get_collections()` - fetch collections from cache or API
  - `clear_collections_cache()` - clear collections cache
- `tag_utils.py` - Tag filtering utilities
  - `is_system_tag(tag_name)` - checks for "unknow", "unread", or date tags (YYYY-MM-DD)
  - `has_real_tags(tags)` - checks if link has non-system tags
  - `filter_system_tags(tags)` / `get_system_tags(tags)`

**Commands** (in `linkwarden/commands/`) - all self-sustainable, read credentials from environment:
- `add.py` - `add_link(url, collection_id, dry_run, unread, silent)` - adds URL with enrichment
- `list_links.py` - `list_links(collection_id)` - lists all links grouped by collection
- `sync.py` - `sync_links(jsonl_path, collection_id, dry_run, limit, show_unmatched)` - syncs descriptions
- `remove_duplicates.py` - `remove_duplicates(dry_run)` - finds and removes duplicates
- `enrich.py` - `enrich_links(prompt_path, collection_id, dry_run, force, limit)` - LLM enrichment
- `enrich.py` - `enrich_links(base_url, token, prompt_path, collection_id, dry_run, force, limit)` - LLM enrichment

## Output structure

```
data/
  newsletters.jsonl       # one JSON per line (scraped newsletters)
  scraped_urls.txt        # for deduplication across runs
  last-fetch_cache.txt    # daily cache timestamp (YYYY-MM-DD)

cache/                    # unified cache directory (managed by cache.py)
  llm.json                # cached LLM enrichment results (per URL, no expiry)
  yt_dlp.json             # cached yt-dlp video info (per URL, 7-day TTL, ~12 KB per video)
  collections.json        # cached collections list (1-day TTL)
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
- `OPENAI_API_KEY` - API key for OpenAI (used by `enrich` command)
- `OPENAI_BASE_URL` - Base URL (optional, for Groq/other OpenAI-compatible providers)
- `OPENAI_MODEL` - Model name (default: `gpt-4o-mini`)
- `OPENAI_USE_RESPONSE_API` - Set to `1` to use Responses API with web search (OpenAI only)

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

Create link:
```
POST /api/v1/links
{
  "name": "Link title",
  "url": "https://example.com/article",
  "description": "...",
  "collectionId": 14,
  "tags": [{"name": "tag1"}, {"name": "tag2"}]
}
```

Note: `/api/v1/links` GET is deprecated, use `/api/v1/search` instead.
