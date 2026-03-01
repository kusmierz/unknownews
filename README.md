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
# Crawl latest 10 newsletters (auto-detects latest issue)
python scraper.py

# Crawl with custom limit
python scraper.py -n 50

# Bypass 3-hour cache and re-fetch
python scraper.py --force

# Start from a specific newsletter URL
python scraper.py https://mrugalski.pl/nl/wu/... -n 20
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

Tools for managing Linkwarden bookmarks: fetch content, enrich with newsletter data and LLM, and remove duplicates.

### Setup

Add to `.env`:
```
LINKWARDEN_TOKEN=your_token_here
LINKWARDEN_URL=https://links.kusmierz.be
OPENAI_API_KEY=sk-...              # for enrich/fetch commands
OPENAI_BASE_URL=                   # optional, for Groq/other providers
OPENAI_MODEL=gpt-4o-mini           # optional, default: gpt-4o-mini
OPENAI_USE_RESPONSE_API=1          # optional, enables Responses API with web search
OPENAI_MODEL_TIER=flex             # optional, service tier (e.g. flex)
```

### Commands

```bash
# Fetch and display content for a URL (standalone, no Linkwarden needed)
python enricher.py <url>                          # render as markdown
python enricher.py <url> --raw                    # raw text only
python enricher.py <url> --force                  # bypass cache, re-fetch
python enricher.py <url> --enrich                 # show LLM enrichment data
python enricher.py <url> --summary                # generate LLM summary
python enricher.py <url> --json                   # output as JSON

# Add a URL to Linkwarden with enrichment
python linkwarden.py add <url>
python linkwarden.py add <url> --collection 14    # specific collection
python linkwarden.py add <url> --dry-run          # preview without adding
python linkwarden.py add <url> --unread           # add with "unread" tag

# List links
python linkwarden.py list                         # all collections
python linkwarden.py list --collection 14         # specific collection

# Enrich links (newsletter data + LLM)
python linkwarden.py enrich-all                   # enrich all collections
python linkwarden.py enrich-all --newsletter-only # newsletter data only (no LLM)
python linkwarden.py enrich-all --llm-only        # LLM only (no newsletter matching)
python linkwarden.py enrich-all --dry-run         # preview (caches results)
python linkwarden.py enrich-all --force           # regenerate all fields
python linkwarden.py enrich-all --collection 14   # specific collection
python linkwarden.py enrich-all --limit 5         # limit processed links
python linkwarden.py enrich-all --show-unmatched  # show URLs not in newsletter

# Remove duplicates
python linkwarden.py remove-duplicates --dry-run  # preview deletions
python linkwarden.py remove-duplicates            # delete duplicates
```

### enricher.py (standalone fetch/enrich tool)

Fetches and renders content for any URL — articles, videos, PDFs, and documents. No Linkwarden dependency.

- **Rendering**: Defaults to markdown display with title and metadata; `--raw` for plain text
- **Content types**: Articles (trafilatura + Playwright fallback), videos (yt-dlp + transcripts), documents (PDF/DOCX/PPTX via markitdown)
- **Enrichment**: `--enrich` runs LLM enrichment and shows title/description/tags/category
- **Summary**: `--summary` generates an LLM summary of the content
- **JSON output**: `--json` outputs structured data (url, content, summary, enrichment fields)
- **Caching**: Content cached 7 days; summaries cached 30 days; `--force` bypasses cache

### Enrich command

Matches bookmarks to newsletter data and enriches with LLM (Polish titles, descriptions, tags):

- **Empty detection**: Only enriches fields that are empty (title = domain, no description, no real tags)
- **Newsletter matching**: Exact URL match first, then fuzzy match by domain+path
- **Force mode**: `--force` regenerates all fields even if not empty
- **Web search**: Set `OPENAI_USE_RESPONSE_API=1` to enable web search via OpenAI Responses API
- **Caching**: LLM results are cached in `cache/llm.json` to save tokens
  - Cache is used on subsequent runs (especially useful with `--dry-run`)
  - Cache entry is removed after successful Linkwarden update
  - Skipped results (LLM couldn't access content) are not cached
- **Limit**: `--limit` counts all processed links (success + failures + skipped)
- **System tags**: Preserves "unknow" and date tags (YYYY-MM-DD) when adding new tags
- **Prompt**: Uses `prompts/enrich-link.md` template
