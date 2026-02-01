import json
import re
import os
from dotenv import load_dotenv
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from rich.console import Console

console = Console(highlight=False)


def clean_text(text: str) -> str:
    """Clean extracted text by removing extra spaces around punctuation."""
    # Replace tabs with spaces
    text = text.replace('\t', ' ')
    # Remove space after opening quotes (but not newlines)
    text = re.sub(r'(["„‟]) +', r'\1', text)
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
    text = re.sub(r'(["„‟]) +', r'\1', text)   # space after opening quote
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
        title = re.sub(r'^\[#uN]\s*', '', title)
        title = re.sub(r'^[🌀?\s]+', '', title)
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
            link_href = link_elem.get("href", "")
            if link_href.startswith("https://uw7.org/"):
                link_href = get_premium_url(link_href)

            links.append({
                "title": link_title,
                "link": link_href,
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


def get_latest_newsletter_url() -> str:
    """Fetch the latest newsletter URL from unknow.news/last."""
    response = requests.get("https://unknow.news/last", allow_redirects=True)
    return response.url


def get_premium_url(url: str) -> str:
    """Convert a newsletter URL to its premium version if applicable."""
    password = os.environ.get("UNKNOW_NEWS_PASSWORD", "")
    data = f"kodx={password}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "curl/8.0.0",
        "Accept": "*/*",
    }
    response = requests.post(
        url,
        headers=headers,
        data=data,
        allow_redirects=False,
        timeout=5,
    )

    return response.headers.get("Location")


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

    # Load successfully scraped URLs from previous runs
    scraped_urls = load_scraped_urls(output_dir)
    initial_count = len(scraped_urls)

    # seen = scraped + processed this run (prevents queue duplicates and re-fetching)
    seen = scraped_urls.copy()
    queue = deque([start_url])
    scraped_count = 0

    with console.status("Fetching...", spinner="dots") as status:
        while queue and scraped_count < max_total:
            url = queue.popleft()

            if url in seen:
                continue
            seen.add(url)

            try:
                newsletter, previous = scrape_newsletter(url)

                # Add previous newsletters to queue for discovery
                for prev in previous:
                    if prev["url"] not in seen:
                        queue.append(prev["url"])

                newsletter["url"] = url
                append_newsletter(newsletter, output_dir)
                scraped_urls.add(url)
                scraped_count += 1

                # Show newsletter
                title = newsletter['title'][:50] + "..." if len(newsletter['title']) > 50 else newsletter['title']
                console.print(f"  [green]+[/green] {newsletter['date']}  [bold]{title}[/bold]")

            except Exception as e:
                console.print(f"  [red]![/red] {url[-40:]}  [dim]{e}[/dim]")

    # Save updated scraped URLs
    save_scraped_urls(scraped_urls, output_dir)

    # Summary line
    if scraped_count:
        console.print(f"\n[green]Scraped {scraped_count} new[/green] ({len(scraped_urls)} total)")
    else:
        console.print(f"\n[dim]No new newsletters[/dim] ({len(scraped_urls)} total)")

    return scraped_count


if __name__ == "__main__":
    import argparse

    load_dotenv()
    parser = argparse.ArgumentParser(description="Crawl unknownews newsletters")
    parser.add_argument("url", nargs="?", help="Starting newsletter URL (default: latest from unknow.news)")
    parser.add_argument("-n", "--limit", type=int, default=10, help="Maximum newsletters to fetch (default: 10)")
    parser.add_argument("-f", "--force", action="store_true", help="Force fetch even if already fetched today")
    args = parser.parse_args()

    console.print("[bold]unknow.news[/bold] scraper\n")

    # Check daily cache
    cache_file = Path("data/cache_last-fetch.txt")
    today = datetime.now().strftime("%Y-%m-%d")
    if cache_file.exists() and not args.force:
        last_fetch = cache_file.read_text().strip()
        if last_fetch == today:
            console.print(f"[dim]Already fetched today. Use --force to re-fetch.[/dim]")
            raise SystemExit(0)

    if args.url:
        start_url = args.url
    else:
        with console.status("Finding latest...", spinner="dots"):
            start_url = get_latest_newsletter_url()

    crawl_newsletters(start_url, max_total=args.limit)

    # Update cache
    cache_file.parent.mkdir(exist_ok=True)
    cache_file.write_text(today)
