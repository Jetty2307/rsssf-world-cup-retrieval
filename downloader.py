import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

START_URL = "https://www.rsssf.org/tablesw/worldcup.html"
ALLOWED_DOMAIN = "rsssf.org"
BLOCKED_PATHS = {"/nersssf.html"}
OUTPUT_DIR = Path("rsssf_worldcup")
DELAY_SECONDS = 1.0
MAX_PAGES = 500  # guard against accidental crawl growth
MAX_DEPTH = 2

OUTPUT_DIR.mkdir(exist_ok=True)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; rsssf-worldcup-mvp-crawler/0.1)"
})

visited = set()
queue = [(START_URL, 0)]


def normalize_url(base_url: str, href: str):
    if not href:
        return None

    # Build an absolute URL
    abs_url = urljoin(base_url, href)

    # Remove #anchor so worldcup.html#goalscorers
    # and worldcup.html are treated as the same page
    abs_url, _ = urldefrag(abs_url)

    parsed = urlparse(abs_url)

    # Allow only http/https
    if parsed.scheme not in {"http", "https"}:
        return None

    hostname = (parsed.hostname or "").lower()

    # Allow only rsssf.org and its subdomains
    if hostname != ALLOWED_DOMAIN and not hostname.endswith(f".{ALLOWED_DOMAIN}"):
        return None

    # Do not enter nersssf.html or anything under it
    normalized_path = parsed.path.rstrip("/") or "/"
    if normalized_path in BLOCKED_PATHS:
        return None

    # Drop query string for consistent normalization
    cleaned = parsed._replace(query="").geturl()

    return cleaned


def url_to_filename(url: str) -> Path:
    parsed = urlparse(url)
    path = parsed.path.strip("/")

    if not path:
        path = "index.html"

    if path.endswith("/"):
        path += "index.html"

    # Preserve the directory structure
    local_path = OUTPUT_DIR / path
    local_path.parent.mkdir(parents=True, exist_ok=True)

    # Add .html when the path has no suffix
    if local_path.suffix == "":
        local_path = local_path.with_suffix(".html")

    return local_path


while queue and len(visited) < MAX_PAGES:
    url, depth = queue.pop(0)

    if url in visited:
        continue

    print(f"Downloading: {url}")
    visited.add(url)

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ERROR: {e}")
        continue

    content_type = resp.headers.get("Content-Type", "").lower()

    # We mostly need HTML pages
    if "text/html" not in content_type:
        print(f"  Skipped non-HTML: {content_type}")
        continue

    # RSSSF can use old encodings; requests usually guesses correctly,
    # but keep a fallback just in case
    if not resp.encoding:
        resp.encoding = "latin-1"

    html = resp.text

    # Save the page
    outfile = url_to_filename(url)
    outfile.write_text(html, encoding="utf-8")
    print(f"  Saved to: {outfile}")

    # Parse outgoing links
    soup = BeautifulSoup(html, "html.parser")

    if depth < MAX_DEPTH:
        queued_urls = {queued_url for queued_url, _ in queue}
        for a in soup.find_all("a", href=True):
            normalized = normalize_url(url, a["href"])
            if normalized and normalized not in visited and normalized not in queued_urls:
                queue.append((normalized, depth + 1))
                queued_urls.add(normalized)

    time.sleep(DELAY_SECONDS)

print(f"\nDone. Downloaded {len(visited)} pages.")
