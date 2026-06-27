import json
import logging
import tempfile
import time

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://learn.foundry.com"
NUKE_VERSION = "17.0"
CONTENT_BASE = f"/nuke/{NUKE_VERSION}/content"
TOC_PATH = f"{CONTENT_BASE}/reference_guide.html"

# Crawl rate: 1 req/sec per robots.txt courtesy
_RATE_LIMIT_SECS = 1


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; NukeDocsBot/1.0)"
    return session


def _fetch(session: requests.Session, url: str) -> BeautifulSoup | None:
    """Fetch a URL and return parsed BeautifulSoup, or None on error."""
    try:
        time.sleep(_RATE_LIMIT_SECS)
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.HTTPError as e:
        logger.warning(f"HTTP {e.response.status_code} fetching {url} — skipping")
        return None
    except requests.RequestException as e:
        logger.warning(f"Request error fetching {url}: {e} — skipping")
        return None


def _absolute(href: str, base_dir: str) -> str:
    """Resolve a relative href against a base directory URL."""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return base_dir.rstrip("/") + "/" + href


def _extract_section_links(toc_soup: BeautifulSoup) -> list[str]:
    """Extract top-level section links from the TOC page.

    TOC page has links like reference_guide/2d_nodes.html, reference_guide/3d_nodes.html.
    """
    links = []
    seen = set()
    for a in toc_soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("reference_guide/") and href.endswith(".html") and href not in seen:
            seen.add(href)
            links.append(f"{BASE_URL}{CONTENT_BASE}/{href}")
    return links


def _extract_subsection_links(section_soup: BeautifulSoup, section_url: str) -> list[str]:
    """Extract subsection links from a section index page.

    Section pages have relative links with a subdirectory, e.g. filter_nodes/filter_nodes.html.
    """
    base_dir = section_url.rsplit("/", 1)[0]
    links = []
    seen = set()
    for a in section_soup.find_all("a", href=True):
        href = a["href"]
        if (
            href.endswith(".html")
            and "/" in href
            and not href.startswith("..")
            and not href.startswith("http")
            and not href.startswith("#")
            and href not in seen
        ):
            seen.add(href)
            links.append(_absolute(href, base_dir))
    return links


def _extract_node_links(subsection_soup: BeautifulSoup, subsection_url: str) -> list[str]:
    """Extract individual node page links from a subsection index page.

    Subsection pages have relative .html links without a sub-path, e.g. blur.html.
    """
    base_dir = subsection_url.rsplit("/", 1)[0]
    links = []
    seen = set()
    for a in subsection_soup.find_all("a", href=True):
        href = a["href"]
        if (
            href.endswith(".html")
            and "/" not in href
            and not href.startswith("#")
            and href not in seen
        ):
            seen.add(href)
            links.append(_absolute(href, base_dir))
    return links


def _parse_node_page(node_soup: BeautifulSoup, url: str) -> dict | None:
    """Extract content from a Nuke node reference page.

    Returns None if the page has too little content to be useful.
    """
    h1 = node_soup.find("h1")
    node_name = h1.get_text(strip=True) if h1 else url.rstrip("/").split("/")[-1].replace(".html", "")

    # Main content lives in div.mc-main-content (verified against live HTML)
    main_div = node_soup.find("div", class_="mc-main-content")
    if not main_div:
        # Fallback to semantic elements
        main_div = node_soup.find("main") or node_soup.find("article") or node_soup.body

    if not main_div:
        return None

    text = main_div.get_text(separator=" ", strip=True)
    word_count = len(text.split())
    if word_count < 100:
        return None  # stub / index page

    # Derive section name from URL path
    # URL structure: .../content/reference_guide/<section_dir>/<subsection_dir>/node.html
    # After CONTENT_BASE prefix, path segments are: reference_guide / section / subsection / node
    path_after_content = url.replace(f"{BASE_URL}{CONTENT_BASE}/", "")
    parts = path_after_content.split("/")
    # parts[0] = "reference_guide", parts[1] = section, parts[2] = subsection, parts[3] = node.html
    section = parts[1] if len(parts) > 2 else "reference_guide"

    sections = _extract_sections(main_div)

    return {"url": url, "node_name": node_name, "section": section, "content": text, "sections": sections}


def _extract_sections(main_div) -> list[dict]:
    """Extract h2-delimited sections from a parsed content div.

    Returns a list of {"title": str, "text": str} dicts. Returns [] when no
    h2 headings are present so callers can fall back to flat chunking.

    Preferred path: h2s are direct children of main_div (recursive=False).
    Fallback path: h2s are nested inside wrapper divs (recursive=True).
    """
    sections = []
    h2_direct = main_div.find_all("h2", recursive=False)

    if h2_direct:
        first_h2 = h2_direct[0]
        intro_parts = []
        for elem in main_div.children:
            if elem is first_h2:
                break
            if hasattr(elem, "get_text"):
                t = elem.get_text(separator=" ", strip=True)
                if t:
                    intro_parts.append(t)
        if intro_parts:
            sections.append({"title": "Overview", "text": " ".join(intro_parts).strip()})

        for h2 in h2_direct:
            title = h2.get_text(strip=True)
            content_parts = []
            for sibling in h2.find_next_siblings():
                if sibling.name == "h2":
                    break
                content_parts.append(sibling.get_text(separator=" ", strip=True))
            section_text = " ".join(content_parts).strip()
            if section_text:
                sections.append({"title": title, "text": section_text})
    else:
        # Fallback: h2s may be nested inside wrapper divs
        for h2 in main_div.find_all("h2"):
            title = h2.get_text(strip=True)
            content_parts = []
            for sibling in h2.find_next_siblings():
                if sibling.find("h2"):
                    break
                content_parts.append(sibling.get_text(separator=" ", strip=True))
            section_text = " ".join(content_parts).strip()
            if section_text:
                sections.append({"title": title, "text": section_text})

    return sections


def scrape_nuke_reference_guide(**context) -> dict:
    """Crawl the Nuke 17.0 reference guide and write scraped pages to a temp file.

    Crawl strategy (3-level):
      TOC → section index pages → subsection index pages → individual node pages

    The scraped data is written to a JSON temp file; the file path is pushed via
    XCom to avoid the Airflow XCom size limit (~2.5 MB for 500 pages × 5 KB).
    """
    session = _make_session()
    toc_url = f"{BASE_URL}{TOC_PATH}"

    logger.info(f"Fetching TOC: {toc_url}")
    toc_soup = _fetch(session, toc_url)
    if not toc_soup:
        raise RuntimeError(f"Failed to fetch TOC page: {toc_url}")

    section_urls = _extract_section_links(toc_soup)
    logger.info(f"Found {len(section_urls)} section pages")

    # Collect all node URLs via subsection pages
    node_urls = []
    for section_url in section_urls:
        logger.info(f"Fetching section: {section_url}")
        section_soup = _fetch(session, section_url)
        if not section_soup:
            continue

        subsection_urls = _extract_subsection_links(section_soup, section_url)
        logger.info(f"  Found {len(subsection_urls)} subsections")

        for subsection_url in subsection_urls:
            logger.info(f"  Fetching subsection: {subsection_url}")
            subsection_soup = _fetch(session, subsection_url)
            if not subsection_soup:
                continue

            links = _extract_node_links(subsection_soup, subsection_url)
            logger.info(f"    Found {len(links)} node pages")
            node_urls.extend(links)

    # Deduplicate
    node_urls = list(dict.fromkeys(node_urls))
    logger.info(f"Total node pages to scrape: {len(node_urls)}")

    pages = []
    for url in node_urls:
        node_soup = _fetch(session, url)
        if not node_soup:
            continue
        page = _parse_node_page(node_soup, url)
        if page:
            pages.append(page)

    logger.info(f"Scraped {len(pages)} content pages from Nuke {NUKE_VERSION} docs")

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", prefix="nuke_pages_", delete=False)
    json.dump(pages, tmp)
    tmp.close()

    ti = context.get("ti")
    if ti:
        ti.xcom_push(key="scraped_file", value=tmp.name)

    return {"pages_scraped": len(pages), "file": tmp.name}
