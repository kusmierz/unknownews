# unknownews scraper

Scraper and crawler for [unknownews](https://unknow.news) newsletter (mrugalski.pl) - extracts structured JSON from newsletter HTML pages and follows links to previous issues automatically.

## Features

- Extracts newsletter metadata (title, date, description)
- Parses all article links with descriptions
- Captures sponsor information with markdown formatting
- Automatically crawls previous newsletters via embedded links
- Deduplication across runs (won't re-scrape existing newsletters)
- Outputs to JSONL format for easy processing

## Requirements

- Python 3.10+
- Dependencies: `requests`, `beautifulsoup4`, `python-dotenv`

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

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Newsletter title with `[#uN] 🌀` prefix removed |
| `date` | string | Publication date in `YYYY-MM-DD` format |
| `description` | string | Intro paragraphs before links (markdown) |
| `sponsor` | string | Sponsor section content (markdown) |
| `links` | array | List of article links |
| `links[].title` | string | Article title |
| `links[].link` | string | Article URL |
| `links[].description` | string | Article description |
| `url` | string | Original newsletter URL |

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

## Linkwarden Sync

Sync newsletter link descriptions and date tags to Linkwarden bookmarks.

### Setup

Add to `.env`:
```
LINKWARDEN_TOKEN=your_token_here
LINKWARDEN_URL=https://links.kusmierz.be
```

### Usage

```bash
# Preview changes (dry run)
python linkwarden_sync.py --dry-run

# Sync to default collection (14)
python linkwarden_sync.py

# Sync to specific collection
python linkwarden_sync.py --collection 14

# Use custom JSONL path
python linkwarden_sync.py --jsonl data/newsletters.jsonl
```

### What it does

- Matches Linkwarden bookmark URLs against newsletter links
- Adds "unknow" tag and date tag (e.g., "2024-12-20") to matched links
- Appends newsletter description to existing bookmark description
