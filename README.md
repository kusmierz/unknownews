# unknownews scraper

Scraper and crawler for [unknownews](https://unknow.news) newsletter (mrugalski.pl) - extracts structured JSON from newsletter HTML pages and follows links to previous issues automatically.

## Features

- Extracts newsletter metadata (title, date, description)
- Parses all article links with descriptions
- Captures sponsor information with Markdown formatting
- Automatically crawls previous newsletters via embedded links
- Deduplication across runs (won't re-scrape existing newsletters)
- Outputs to JSONL format for easy processing

## Requirements

- Python 3.10+
- Dependencies: `requests`, `beautifulsoup4`, `python-dotenv`, `rich`, `openai`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

### CLI

```bash
# Crawl 10 newsletters (default)
python scraper.py https://mrugalski.pl/nl/wu/u8d1L2kQOHGVezsjqUWH0g

# Crawl with custom limit
python scraper.py https://mrugalski.pl/nl/wu/u8d1L2kQOHGVezsjqUWH0g -n 50

# Resume crawling (automatically skips already scraped URLs)
python scraper.py https://mrugalski.pl/nl/wu/u8d1L2kQOHGVezsjqUWH0g -n 200
```

### Python API

```python
from scraper import scrape_newsletter, crawl_newsletters

# Scrape single newsletter (returns newsletter dict + list of previous newsletter links)
newsletter, previous = scrape_newsletter("https://mrugalski.pl/nl/wu/...")

# Crawl multiple newsletters following 'previous' links
count = crawl_newsletters("https://mrugalski.pl/nl/wu/...", max_total=50)
```

## Output

Crawled data is saved to `data/` directory:
- `newsletters.jsonl` - one JSON object per line
- `scraped_urls.txt` - URLs already scraped (for deduplication across runs)

### JSON Schema

Each line in `newsletters.jsonl` contains a newsletter object:

```json
{
  "title": "string - Newsletter title (prefix stripped)",
  "date": "string - ISO date format YYYY-MM-DD",
  "description": "string - Intro text with markdown formatting",
  "sponsor": "string - Sponsor section with markdown formatting",
  "links": [
    {
      "title": "string - Article title",
      "link": "string - Article URL",
      "description": "string - Article description (from INFO: field)"
    }
  ],
  "url": "string - Source newsletter URL"
}
```

| Field                 | Type   | Description                                     |
|-----------------------|--------|-------------------------------------------------|
| `title`               | string | Newsletter title with `[#uN] 🌀` prefix removed |
| `date`                | string | Publication date in `YYYY-MM-DD` format         |
| `description`         | string | Intro paragraphs before links (markdown)        |
| `sponsor`             | string | Sponsor section content (markdown)              |
| `links`               | array  | List of article links                           |
| `links[].title`       | string | Article title                                   |
| `links[].link`        | string | Article URL                                     |
| `links[].description` | string | Article description                             |
| `url`                 | string | Original newsletter URL                         |

### Working with the data

```bash
# Pretty print all newsletters
jq '.' data/newsletters.jsonl

# List titles and dates
jq -r '[.date, .title] | @tsv' data/newsletters.jsonl | sort

# Count total links across all newsletters
jq -s '[.[].links | length] | add' data/newsletters.jsonl

# Extract all article URLs
jq -r '.links[].link' data/newsletters.jsonl

# Find newsletters mentioning a topic
jq 'select(.links[].title | test("AI"; "i"))' data/newsletters.jsonl
```

## Linkwarden Tools

Tools for managing Linkwarden bookmarks: sync newsletter descriptions, enrich with LLM, and remove duplicates.

### Setup

Add to `.env`:
```
LINKWARDEN_TOKEN=your_token_here
LINKWARDEN_URL=https://links.kusmierz.be
OPENAI_API_KEY=sk-...              # for enrich command
OPENAI_BASE_URL=                   # optional, for Groq/other providers
OPENAI_MODEL=gpt-4o-mini           # optional, default: gpt-4o-mini
OPENAI_USE_RESPONSE_API=1          # optional, enables Response API
```

### Commands

```bash
# List links
python linkwarden.py list                         # all collections
python linkwarden.py list --collection 14         # specific collection

# Sync newsletter descriptions
python linkwarden.py sync --dry-run               # preview changes
python linkwarden.py sync                         # sync all collections
python linkwarden.py sync --collection 14         # specific collection
python linkwarden.py sync --limit 10              # limit updates

# Enrich links with LLM
python linkwarden.py enrich --dry-run             # preview (caches results)
python linkwarden.py enrich                       # enrich empty fields
python linkwarden.py enrich --force               # regenerate all fields
python linkwarden.py enrich --collection 14       # specific collection
python linkwarden.py enrich --limit 5             # limit processed (including failures)

# Remove duplicates
python linkwarden.py remove-duplicates --dry-run  # preview deletions
python linkwarden.py remove-duplicates            # delete duplicates
```

### Sync command

Matches Linkwarden bookmarks to newsletter links and updates metadata:

- **URL matching**: Exact match first, then fuzzy match (by domain+path, ignoring query params)
- **URL normalization**: Removes tracking params (`utm_*`, `fbclid`, etc.) and fragments (`#`)
- **Name update**: Sets link name to newsletter title with original in brackets
- **Tags**: Adds "unknow" tag and date tag (e.g., "2024-12-20")
- **Description**: Appends newsletter description to existing bookmark description

### Enrich command

Uses LLM (OpenAI or compatible) to generate Polish titles, descriptions, and tags for bookmarks:

- **Empty detection**: Only enriches fields that are empty (title = domain, no description, no real tags)
- **Force mode**: `--force` regenerates all fields even if not empty
- **Web search**: Set `OPENAI_USE_RESPONSE_API=1` to enable web search via OpenAI Responses API
- **Caching**: LLM results are cached in `data/llm_cache.json` to save tokens
  - Cache is used on subsequent runs (especially useful with `--dry-run`)
  - Cache entry is removed after successful Linkwarden update
  - Skipped results (LLM couldn't access content) are not cached
- **Limit**: `--limit` counts all processed links (success + failures + skipped)
- **System tags**: Preserves "unknow" and date tags (YYYY-MM-DD) when adding new tags
- **Prompt**: Uses `prompts/enrich-link.md` template (customizable with `--prompt`)
