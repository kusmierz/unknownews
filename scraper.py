import json
import re
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


def clean_text(text: str) -> str:
    """Clean extracted text by removing extra spaces around punctuation."""
    # Replace tabs with spaces
    text = text.replace('\t', ' ')
    # Remove space after opening quotes (but not newlines)
    text = re.sub(r'(["\„\"]) +', r'\1', text)
    # Remove space before punctuation
    text = re.sub(r' +([.,;:!?])', r'\1', text)
    # Normalize multiple spaces
    text = re.sub(r' +', ' ', text)
    # Remove leading spaces on lines
    text = re.sub(r'\n +', '\n', text)
    return text.strip()


def html_to_markdown(element) -> str:
    """Convert HTML element to markdown text."""
    if element is None:
        return ""

    parts = []
    for child in element.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.name == "strong" or child.name == "b":
            inner = html_to_markdown(child)
            parts.append(f"**{inner}**")
        elif child.name == "em" or child.name == "i":
            inner = html_to_markdown(child)
            parts.append(f"*{inner}*")
        elif child.name == "a":
            href = child.get("href", "")
            text = html_to_markdown(child)
            # If link text is the URL itself, just use the URL
            if text.strip() == href or text.strip().startswith("http"):
                parts.append(href)
            else:
                parts.append(f"[{text}]({href})")
        elif child.name == "br":
            parts.append("\n")
        elif child.name in ("p", "div"):
            parts.append(html_to_markdown(child))
            parts.append("\n\n")
        elif child.name == "ul" or child.name == "ol":
            for li in child.find_all("li", recursive=False):
                parts.append(f"- {html_to_markdown(li).strip()}\n")
            parts.append("\n")
        elif child.name == "li":
            parts.append(html_to_markdown(child))
        elif child.name == "span":
            parts.append(html_to_markdown(child))
        elif hasattr(child, "children"):
            parts.append(html_to_markdown(child))
        else:
            parts.append(child.get_text())

    text = "".join(parts)
    # Clean up but preserve newlines
    text = text.replace('\t', ' ')               # tabs to spaces
    text = re.sub(r'(["\„\"]) +', r'\1', text)   # space after opening quote
    text = re.sub(r' +([.,;:!?])', r'\1', text)  # space before punctuation
    text = re.sub(r' +', ' ', text)              # multiple spaces
    text = re.sub(r'\n +', '\n', text)           # leading spaces on lines
    return text


def scrape_newsletter(url: str) -> tuple[dict, list[dict]]:
    """
    Scrape newsletter from mrugalski.pl

    Returns:
        tuple: (newsletter_data, previous_newsletters)
    """
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    # Extract title from <title> tag, removing prefix like "[#uN] 🌀 " or "? "
    title_tag = soup.find("title")
    title = ""
    if title_tag:
        title = title_tag.get_text(strip=True)
        # Remove common prefixes: [#uN], emojis, question marks, etc.
        title = re.sub(r'^\[#uN\]\s*', '', title)
        title = re.sub(r'^[🌀\?\s]+', '', title)
        title = title.strip()

    # Extract date from og:image URL (e.g., https://img.unknow.news/og/20260123.png)
    date = ""
    og_image = soup.find("meta", property="og:image")
    if og_image:
        img_url = og_image.get("content", "")
        date_match = re.search(r'/og/(\d{8})\.png', img_url)
        if date_match:
            d = date_match.group(1)
            date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    # Extract description (text before <ol>) and sponsor
    description_parts = []
    sponsor = ""

    ol = soup.find("ol")

    # Find sponsor div by its background style
    sponsor_div = None
    for elem in ol.find_previous_siblings():
        if elem.name == "div":
            style = elem.get("style", "")
            if "background:#eeeeee" in style or "background: #eeeeee" in style:
                sponsor_div = elem
                break

    # Extract sponsor content from div with markdown formatting
    if sponsor_div:
        sponsor = html_to_markdown(sponsor_div)
        # Normalize multiple newlines
        sponsor = re.sub(r'\n\s*\n', '\n\n', sponsor).strip()

    # Collect description paragraphs (between greeting and sponsor marker)
    # Elements are in reverse order: closest to <ol> first, greeting last
    # If no sponsor section exists (old format), collect all paragraphs after closing
    has_sponsor_section = sponsor_div is not None
    in_description = False
    past_closing = False
    for elem in ol.find_previous_siblings():
        text = elem.get_text(strip=True)
        if not text:
            continue

        # Skip closing paragraphs (before sponsor section in page order)
        if "◢ #unknownews ◣" in text or "Zapraszam do lektury" in text:
            past_closing = True
            continue

        # Start collecting after passing sponsor div
        if elem == sponsor_div:
            in_description = True
            continue

        # Skip and start collecting after passing marker paragraph (case insensitive)
        text_lower = text.lower()
        if "pora na sponsora" in text_lower or "info o promocji" in text_lower:
            in_description = True
            continue

        # Old format without sponsor: collect after passing closing paragraphs
        if not has_sponsor_section and past_closing:
            in_description = True

        if in_description and elem.name == "p":
            description_parts.insert(0, html_to_markdown(elem))

    description = "\n\n".join(description_parts)

    # Extract links from <ol>
    links = []
    for li in soup.select("ol li"):
        title_elem = li.find("strong")
        link_elem = li.find("a")

        # Find description - try span first (new format), then plain text (old format)
        desc_text = ""
        for span in li.find_all("span"):
            text = span.get_text(strip=True)
            if text.startswith("INFO:"):
                desc_text = re.sub(r"^INFO:\s*", "", span.get_text(separator=" ", strip=True))
                break

        # Old format: INFO: is plain text in the li/p element
        if not desc_text:
            li_text = li.get_text(separator=" ", strip=True)
            info_match = re.search(r"INFO:\s*(.+)$", li_text)
            if info_match:
                desc_text = info_match.group(1)

        if title_elem and link_elem:
            # Remove number prefix like "1. ", "12. " etc.
            link_title = re.sub(r"^\d+\.\s*", "", title_elem.get_text(separator=" ", strip=True))

            links.append({
                "title": link_title,
                "link": link_elem.get("href"),
                "description": desc_text
            })

    # Extract previous newsletters from <ul> at the bottom
    previous_newsletters = []
    for ul in soup.find_all("ul"):
        for li in ul.find_all("li"):
            date_elem = li.find(["strong", "b"])
            a = li.find("a")
            if date_elem and a:
                date_match = re.search(r"\d{4}-\d{2}-\d{2}", date_elem.get_text())
                if date_match:
                    previous_newsletters.append({
                        "url": a.get("href"),
                        "date": date_match.group(),
                        "title": a.get_text(separator=" ", strip=True)
                    })

    # Fallback: if no date found, add 7 days to newest previous newsletter date
    if not date and previous_newsletters:
        newest_prev_date = max(p["date"] for p in previous_newsletters)
        prev_dt = datetime.strptime(newest_prev_date, "%Y-%m-%d")
        date = (prev_dt + timedelta(days=7)).strftime("%Y-%m-%d")

    newsletter = {
        "title": title,
        "date": date,
        "description": description,
        "sponsor": sponsor,
        "links": links
    }

    return newsletter, previous_newsletters


def load_scraped_urls(output_dir: str) -> set[str]:
    """Load set of already scraped URLs from file."""
    path = Path(output_dir) / "scraped_urls.txt"
    if path.exists():
        return set(path.read_text().strip().split("\n"))
    return set()


def save_scraped_urls(urls: set[str], output_dir: str) -> None:
    """Save scraped URLs to file."""
    path = Path(output_dir) / "scraped_urls.txt"
    path.write_text("\n".join(sorted(urls)))


def append_newsletter(newsletter: dict, output_dir: str) -> None:
    """Append newsletter to JSONL file."""
    path = Path(output_dir) / "newsletters.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(newsletter, ensure_ascii=False) + "\n")


def crawl_newsletters(
    start_url: str,
    max_total: int = 50,
    output_dir: str = "data"
) -> int:
    """
    Crawl newsletters starting from URL, following 'previous' links.

    Args:
        start_url: Starting newsletter URL
        max_total: Maximum newsletters to scrape
        output_dir: Directory for output files

    Returns:
        Number of newly scraped newsletters
    """
    # Create output dir
    Path(output_dir).mkdir(exist_ok=True)

    # Load already scraped URLs
    scraped_urls = load_scraped_urls(output_dir)
    initial_count = len(scraped_urls)
    if initial_count:
        print(f"Found {initial_count} existing newsletters, fetching up to {max_total} total...")

    # Queue of URLs to scrape, visited tracks URLs we've processed this run
    queue = deque([start_url])
    visited = set()
    scraped_count = 0

    while queue and (initial_count + scraped_count) < max_total:
        url = queue.popleft()

        if url in visited:
            continue
        visited.add(url)

        already_scraped = url in scraped_urls

        try:
            newsletter, previous = scrape_newsletter(url)

            # Add previous newsletters to queue (even if current is already scraped)
            for prev in previous:
                if prev["url"] not in visited:
                    queue.append(prev["url"])

            if already_scraped:
                continue

            newsletter["url"] = url
            print(f"Scraping: {newsletter['date']} - {newsletter['title'][:50]}...")

            append_newsletter(newsletter, output_dir)
            scraped_urls.add(url)
            scraped_count += 1

        except Exception as e:
            print(f"Error scraping {url}: {e}")
            continue

    # Save updated scraped URLs
    save_scraped_urls(scraped_urls, output_dir)

    return scraped_count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl unknownews newsletters")
    parser.add_argument("url", help="Starting newsletter URL")
    parser.add_argument("-n", "--limit", type=int, default=10, help="Maximum total newsletters (default: 10)")
    args = parser.parse_args()

    count = crawl_newsletters(args.url, max_total=args.limit)
    print(f"\nScraped {count} new newsletters")
