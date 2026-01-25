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

# Sync to Linkwarden
python linkwarden_sync.py --dry-run     # preview
python linkwarden_sync.py               # sync to collection 14
python linkwarden_sync.py --collection 14
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
Syncs newsletter descriptions to Linkwarden bookmarks. Main functions:

- `load_newsletter_index(jsonl_path)` -> `dict[str, dict]` - URL to {description, date, title}
- `fetch_collection_links(base_url, collection_id, token)` -> `list[dict]` - GET with pagination
- `update_link(base_url, link_id, description, tags, token)` -> `bool` - PUT to update
- `sync_links(base_url, collection_id, jsonl_path)` - main sync logic

Helper: `normalize_url(url)` - lowercase, strip trailing slash, http->https

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

Fetch links: `GET /api/v1/links?collectionId=X&sort=0&cursor=N`
Update link: `PUT /api/v1/links` with body:
```json
{
  "links": [123],
  "removePreviousTags": false,
  "newData": {
    "description": "...",
    "tags": [{"name": "unknow"}, {"name": "2024-12-20"}]
  }
}
```
