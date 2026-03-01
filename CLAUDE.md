# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tools

- **Context7 MCP** is available for looking up library documentation. Use `resolve-library-id` then `query-docs` to get up-to-date docs and code examples for any dependency.

## Project overview

Python scraper and crawler for unknownews newsletter (mrugalski.pl). Extracts structured JSON from newsletter HTML pages with automatic crawling of previous issues.

## Commands

```bash
source .venv/bin/activate        # activate virtualenv
pip install -r requirements.txt  # install deps

# Crawl newsletters (with 3-hour caching)
python scraper.py [-n LIMIT] [-f]                 # fetch latest (default: max 10, cached 3h)
python scraper.py -n 50                           # fetch up to 50 newsletters
python scraper.py --force                         # bypass 3-hour cache
python scraper.py <url> -n 20                     # start from specific URL

# Standalone content fetcher / enricher (no Linkwarden dependency)
python enricher.py <url>                          # fetch and render content as markdown
python enricher.py <url> --raw                    # raw text only
python enricher.py <url> --force                  # bypass cache, re-fetch
python enricher.py <url> --enrich                 # show LLM enrichment (runs if not cached)
python enricher.py <url> --summary                # generate LLM summary
python enricher.py <url> --json                   # output as JSON
python enricher.py <url> --enrich --summary       # enrichment + summary
python enricher.py <url> -v                       # fetch details

# Add URL to Linkwarden (with newsletter or LLM enrichment)
python linkwarden.py add <url>                    # add to Uncategorized (with warning)
python linkwarden.py add <url> --dry-run          # preview without adding
python linkwarden.py add <url> --collection 14    # specify target collection
python linkwarden.py add <url> --unread           # add with "unread" tag
python linkwarden.py add <url> --silent           # no output, just exit code

# Verbosity levels (all commands)
python linkwarden.py <cmd> -v                     # short diagnostics (fetch info, cache hits)
python linkwarden.py <cmd> -vv                    # full details (LLM prompts, config, response)

# List links in Linkwarden
python linkwarden.py list                    # list all links grouped by collection
python linkwarden.py list --collection 14   # list links from specific collection

# Enrich links (newsletter data + LLM)
python linkwarden.py enrich-all                       # newsletter match + LLM (default)
python linkwarden.py enrich-all --newsletter-only     # newsletter data only (no LLM)
python linkwarden.py enrich-all --llm-only            # LLM only (no newsletter matching)
python linkwarden.py enrich-all --collection 14       # specific collection
python linkwarden.py enrich-all --force               # overwrite all LLM fields
python linkwarden.py enrich-all --dry-run             # preview without updating
python linkwarden.py enrich-all --limit 5             # limit processed links
python linkwarden.py enrich-all --show-unmatched      # show URLs not in newsletter
python linkwarden.py enrich-all -v                    # short diagnostics
python linkwarden.py enrich-all -vv                   # full details incl. LLM prompts

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
- Uses `cache/last-fetch.txt` to track last fetch time
- Only fetches once per 3 hours (bypass with `--force`)

### Module dependency order

```
common/ ← transcriber/ ← enricher/ ← linkwarden/
                                    ↑
                          enricher.py (standalone CLI)
```

### enricher.py (standalone CLI entry point)
Thin wrapper around `enricher/cli.py`. Fetches and displays content for any URL without Linkwarden dependency.

### linkwarden.py (main CLI)
Thin entry point (~15 lines). Imports `linkwarden.cli.main` and dispatches to command implementations. Commands: `add`, `list`, `enrich-all`, `remove-duplicates`.

### common/ (shared utilities — no project imports)
- `cache.py` - Unified cache service for all cache types
  - `get_cache(key, cache_type, max_age_days)` - get cached value with optional expiration
  - `set_cache(key, value, cache_type, ttl_days)` - set cache with optional TTL
  - `remove_cache(key, cache_type)` - remove specific cache entry
  - `clear_cache_type(cache_type)` - clear all cache for a type
- `display.py` - Rich console formatting
  - `console` - global Rich Console instance
  - `show_diff(old, new, indent, muted)` - displays inline diff
  - `get_tag_color(tag_name)` - consistent tag colors
  - `format_tags_display(tags)` - format list of tag names as colored Rich markup string
- `url_utils.py` - URL normalization and matching
  - `normalize_url(url)` - removes fragments, tracking params, normalizes http->https
  - `get_url_path_key(url)` - extracts domain+path for fuzzy matching
  - `filter_query_params(query, keep_only)` - filters query parameters
- `fetcher_utils.py` - Shared utilities and exceptions for content fetchers
  - `truncate_content(text, max_chars)` - intelligent sentence-boundary truncation
  - `format_duration(seconds)` - converts seconds to human-readable duration (e.g. "1h 5m 30s")
  - `format_duration_short(seconds)` - rounded short duration for titles (e.g. "54m", "~2.5h")
  - `is_video_url(url)` - URL-based video platform detection
  - `check_url_head(url)` - HEAD request to check reachability and content type
  - `is_document_content_type(content_type)` - detect document MIME type (returns "pdf"/"docx"/etc or None)
  - `is_document_url(url)` - detect document type from URL extension (fallback to MIME check)
  - Exceptions: `ContentFetchError`, `RateLimitError`

### transcriber/ (video/audio transcription)
- `video_fetcher.py` - `fetch_video_content(url)` - uses yt-dlp for metadata + youtube-transcript-api for transcripts (cached 7 days, ~10 KB per video)
- `transcript.py` - `extract_transcript_from_info(info_dict, verbose)` - extracts transcript via youtube-transcript-api (languages: original → en → pl)
- `local.py` - stub for local video transcription (`NotImplementedError`)
- `yt_dlp_cache.py` - Thin wrapper around unified cache for yt-dlp video info (7-day TTL)

### enricher/ (generic content enrichment — no Linkwarden deps)
- `content_fetcher.py` - `fetch_content(url, verbose, force)` - orchestrates fetching by URL type (article, video, document, playwright fallback)
- `format.py` - `format_content_for_llm(content_data)` - formats fetch_content() output as XML for LLM
- `content_enricher.py` - `enrich_url(url, prompt_path, verbose, extra_context, status)` - cache check → fetch → enrich (generic, no Linkwarden fallback)
- `article_fetcher.py` - `fetch_article_content(url)` - uses trafilatura; falls back to Playwright
- `document_fetcher.py` - `fetch_document_content(url, doc_type)` - PDF/DOCX/PPTX/XLSX via markitdown
- `llm.py` - Generic OpenAI-compatible API client
  - `call_api(user_prompt, system_prompt, max_retries, verbose, file_url, json_mode)` - orchestrator with retry
  - `call_responses_api(...)` - OpenAI Responses API with web search
  - `call_chat_completions_api(...)` - standard Chat Completions API
- `enrich_llm.py` - LLM enrichment utilities
  - `enrich_content(url, formatted_content, original_title, prompt_path, verbose, file_url)` - calls LLM and caches result
  - `load_prompt(prompt_path)` - loads prompt template file
  - `parse_json_response(text)` - parses JSON from LLM response, decodes HTML entities
  - `is_title_empty(name, url)` - checks if title is empty, domain-only, or bogus (e.g. "Just a moment...")
  - `has_llm_title(name)` - checks if title already has LLM bracket format "LLM title [Original]"
  - `is_description_empty(description)` - checks if description is empty/whitespace
- `summary_llm.py` - `summarize_url(url, verbose, force)` / `summarize_content(content_data, verbose)`
- `title_utils.py` - `format_enriched_title(llm_title, original_title)` - bracket notation formatting
- `cli.py` - CLI logic for `enricher.py` (no Linkwarden/newsletter deps)
- `llm_cache.py` - Thin wrapper around unified cache for LLM results (no expiry)
- `summary_cache.py` - Thin wrapper around unified cache for LLM summaries (30-day TTL)
- `article_cache.py` - Thin wrapper around unified cache for article content (7-day TTL)

### linkwarden/ (Linkwarden-specific sync/API/commands)
**Core modules:**
- `config.py` - `get_api_config()` - reads LINKWARDEN_URL and LINKWARDEN_TOKEN from environment
- `api.py` - Linkwarden API client
  - `fetch_all_collections()`, `fetch_collection_links(collection_id)`, `update_link(...)`, `create_link(...)`, `delete_link(link_id)`
- `links.py` - Link operations facade (re-exports API functions + orchestration)
  - `fetch_all_links(silent)`, `iter_all_links(silent)`, `iter_collection_links(collection_id)`
- `newsletter.py` - `load_newsletter_index()` → `(exact_index, fuzzy_index)`, `match_newsletter(link, ...)`
- `duplicates.py` - `find_duplicates(links)` → `(exact_groups, fuzzy_groups)`
- `collections_cache.py` - `get_collections()` / `clear_collections_cache()` (1-day TTL)
- `tag_utils.py` - Tag filtering and creation
  - `is_system_tag(tag_name)` - checks for "unknow", "unread", or date tags (YYYY-MM-DD)
  - `has_real_tags(tags)` / `filter_system_tags(tags)` / `get_system_tags(tags)`
  - `build_newsletter_tags(nl_data)` - returns `["unknow", date]` from newsletter data
- `lw_content.py` - `fetch_linkwarden_content(link)` - fetches content using Linkwarden link dict as fallback
- `lw_enricher.py` - Linkwarden-aware enrichment wrapper
  - `enrich_link(url, prompt_path, verbose, link, status, extra_context)` - wraps `enricher.enrich_url()` with Linkwarden fallback
  - `needs_enrichment(link, force)` - checks which fields need enrichment (Linkwarden tag format)
  - Re-exports: `is_title_empty`, `has_llm_title`, `is_description_empty`, `enrich_content`, `RateLimitError`
- `cli.py` - `build_parser()` / `dispatch(args)` / `main()` - argparse setup extracted from linkwarden.py

**Commands** (in `linkwarden/commands/`) - all self-sustainable, read credentials from environment:
- `add.py` - `add_link(url, collection_id, dry_run, unread, silent)` - adds URL with enrichment
- `enrich_all.py` - `enrich_all_links(...)` - newsletter + LLM enrichment for existing links
- `list_links.py` - `list_links(collection_id)` - lists all links grouped by collection
- `remove_duplicates.py` - `remove_duplicates(dry_run)` - finds and removes duplicates

## Output structure

```
data/
  newsletters.jsonl       # one JSON per line (scraped newsletters)
  scraped_urls.txt        # for deduplication across runs

cache/                    # unified cache directory (managed by cache.py)
  last-fetch.txt          # 3-hour fetch cache timestamp (ISO datetime)
  article.json            # cached article content (per URL, 7-day TTL)
  llm.json                # cached LLM enrichment results (per URL, no expiry)
  summary.json            # cached LLM summaries (per URL, 30-day TTL)
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
- `OPENAI_MODEL_TIER` - Optional service tier (e.g., `flex` for OpenAI Flex processing)

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
