from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .chapter_cleaner import clean_html_to_text


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,vi;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


@dataclass
class FetchedPage:
    url: str
    html: str
    final_url: str


_CHARSET_RE = re.compile(rb'charset=["\']?([\w\-]+)', re.IGNORECASE)


def _decode_html(content: bytes, declared_charset: str = "") -> str:
    candidates: list[str] = []
    declared = (declared_charset or "").strip().lower()
    if declared:
        candidates.append(declared)
    m = _CHARSET_RE.search(content[:4096])
    if m:
        meta = m.group(1).decode("ascii", errors="ignore").lower()
        if meta:
            candidates.append(meta)
    for enc in ("utf-8", "gb18030", "gbk", "gb2312", "big5", "latin-1"):
        if enc not in candidates:
            candidates.append(enc)
    for enc in candidates:
        try:
            return content.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", errors="ignore")


def _charset_from_content_type(content_type: str) -> str:
    m = re.search(r"charset=([\w\-]+)", content_type, re.IGNORECASE)
    return m.group(1) if m else ""


def _referer_for(url: str) -> Optional[str]:
    parsed = urlparse(url)
    path = parsed.path or ""
    m = re.match(r"^/txt/(\d+)/", path, re.IGNORECASE)
    if m:
        return f"{parsed.scheme}://{parsed.netloc}/book/{m.group(1)}/"
    m = re.match(r"^/book/(\d+)/", path, re.IGNORECASE)
    if m:
        return f"{parsed.scheme}://{parsed.netloc}/book/{m.group(1)}/"
    return None


def _build_headers(url: str) -> dict:
    headers = dict(DEFAULT_HEADERS)
    ref = _referer_for(url)
    if ref:
        headers["Referer"] = ref
    return headers


def fetch_with_httpx(url: str, timeout: int = 30) -> FetchedPage:
    with httpx.Client(
        headers=_build_headers(url),
        follow_redirects=True,
        timeout=timeout,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        html = _decode_html(resp.content, _charset_from_content_type(content_type))
        final_url = str(resp.url)
        return FetchedPage(url=url, html=html, final_url=final_url)


def fetch_with_curl_cffi(url: str, timeout: int = 30) -> FetchedPage:
    try:
        from curl_cffi import requests as cffi_requests
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"curl_cffi is not available: {e}")

    resp = cffi_requests.get(
        url,
        headers=_build_headers(url),
        impersonate="chrome",
        timeout=timeout,
        allow_redirects=True,
    )
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    html = _decode_html(resp.content, _charset_from_content_type(content_type))
    final_url = str(resp.url)
    return FetchedPage(url=url, html=html, final_url=final_url)


def fetch_with_playwright(url: str, timeout: int = 30) -> FetchedPage:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"Playwright is not available: {e}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=DEFAULT_HEADERS["User-Agent"],
                locale="zh-CN",
                extra_http_headers={
                    "Accept-Language": DEFAULT_HEADERS["Accept-Language"],
                },
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(800)
            html = page.content()
            final_url = page.url
            return FetchedPage(url=url, html=html, final_url=final_url)
        finally:
            browser.close()


def smart_fetch(
    url: str,
    timeout: int = 30,
    allow_curl_cffi: bool = True,
    allow_playwright: bool = False,
) -> FetchedPage:
    primary_error: Exception | None = None
    try:
        return fetch_with_httpx(url, timeout=timeout)
    except Exception as e:
        primary_error = e

    if allow_curl_cffi:
        try:
            return fetch_with_curl_cffi(url, timeout=timeout)
        except Exception:
            pass

    if allow_playwright:
        return fetch_with_playwright(url, timeout=timeout)

    raise primary_error


@dataclass
class ParsedNovel:
    title: str
    description: Optional[str]
    chapters: list["ParsedChapter"]


@dataclass
class ParsedChapter:
    title: str
    url: str


def _normalize_url(base: str, href: str) -> str:
    return urljoin(base, href)


def _looks_like_chapter_link(href: str) -> bool:
    if not href:
        return False
    if href.startswith(("javascript:", "#", "mailto:")):
        return False
    if re.search(r"\.html?($|\?)", href, re.IGNORECASE):
        return True
    if re.search(r"/txt/\d+/\d+", href, re.IGNORECASE):
        return True
    if re.search(r"/book/\d+/\d+\.html?$", href, re.IGNORECASE):
        return True
    return False


def parse_69shuba_index(html: str, base_url: str) -> ParsedNovel:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("h1, .bookinfo .info h1, .bookname, #info h1")
    title = title_el.get_text(strip=True) if title_el else "Untitled"

    desc_el = soup.select_one("#intro, .intro, .bookinfo .desc, .description")
    description = desc_el.get_text(strip=True) if desc_el else None

    seen_urls: set[str] = set()
    chapters: list[ParsedChapter] = []
    for a in soup.select("a"):
        href = a.get("href", "") or ""
        if not _looks_like_chapter_link(href):
            continue
        parsed = urlparse(href)
        path = parsed.path or ""
        if "/txt/" not in path and not re.search(r"/book/\d+/\d+\.html?$", path, re.IGNORECASE):
            continue
        text = a.get_text(strip=True)
        if not text or len(text) > 120:
            continue
        url = _normalize_url(base_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        text_clean = re.sub(r"\d{4}-\d{2}-\d{2}$", "", text).strip()
        chapters.append(ParsedChapter(title=text_clean, url=url))

    return ParsedNovel(title=title, description=description, chapters=chapters)


def parse_chapter_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    chapter_el = None
    for sel in [
        "#content", ".content",
        "#chaptercontent", ".chaptercontent",
        ".txtnav", "#txtnav",
        ".readcontent", "#readcontent",
        "#bookcontent", ".novel_content",
        "#nr1", ".nr1", "#nr_content", "#content_text",
    ]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            chapter_el = el
            break
    if chapter_el is None:
        candidates = soup.find_all(["div", "section", "article"])
        if candidates:
            chapter_el = max(candidates, key=lambda e: len(e.get_text(strip=True)))
    target = str(chapter_el) if chapter_el is not None else html
    text = clean_html_to_text(target)
    lines = [ln for ln in text.split("\n") if ln.strip()]
    cleaned: list[str] = []
    skip_phrases = ("首页", "书页", "收藏", "目录", "设置", "白天", "黑夜", "夜间", "上一章", "下一章", "返回目录", "加入书签")
    for ln in lines:
        s = ln.strip()
        if s in skip_phrases:
            continue
        if s.startswith(">") or "69书吧" in s or "69shuba" in s:
            continue
        cleaned.append(ln)
    return "\n".join(cleaned).strip()


def is_69shuba(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return "69shuba" in host


def _69shuba_catalog_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    path = parsed.path or ""
    m = re.match(r"^(/book/)(\d+)\.html?$", path, re.IGNORECASE)
    if m:
        return f"{parsed.scheme}://{parsed.netloc}{m.group(1)}{m.group(2)}/"
    if re.match(r"^/book/\d+/$", path):
        return url
    return None


def import_from_url(url: str, timeout: int = 30, allow_curl_cffi: bool = True, allow_playwright: bool = False) -> ParsedNovel:
    page = smart_fetch(url, timeout=timeout, allow_curl_cffi=allow_curl_cffi, allow_playwright=allow_playwright)
    if is_69shuba(url):
        novel = parse_69shuba_index(page.html, page.final_url)
        catalog_url = _69shuba_catalog_url(page.final_url)
        if catalog_url and (catalog_url != page.final_url or len(novel.chapters) < 20):
            try:
                catalog_page = smart_fetch(
                    catalog_url,
                    timeout=timeout,
                    allow_curl_cffi=allow_curl_cffi,
                    allow_playwright=allow_playwright,
                )
                catalog_novel = parse_69shuba_index(catalog_page.html, catalog_page.final_url)
                if catalog_novel.title and (novel.title == "Untitled" or not novel.title):
                    novel.title = catalog_novel.title
                if catalog_novel.description and not novel.description:
                    novel.description = catalog_novel.description
                if len(catalog_novel.chapters) > len(novel.chapters):
                    novel.chapters = catalog_novel.chapters
            except Exception:
                pass
    else:
        novel = parse_generic_index(page.html, page.final_url)
    if not novel.title or novel.title == "Untitled":
        soup = BeautifulSoup(page.html, "lxml")
        if soup.title and soup.title.string:
            novel.title = soup.title.string.strip()
    return novel


def parse_generic_index(html: str, base_url: str) -> ParsedNovel:
    soup = BeautifulSoup(html, "lxml")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    chapters: list[ParsedChapter] = []
    for a in soup.select("a"):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if not href or not text:
            continue
        if not re.search(r"\.html?($|\?)", href, re.IGNORECASE):
            continue
        url = _normalize_url(base_url, href)
        chapters.append(ParsedChapter(title=text, url=url))

    return ParsedNovel(title=title or "Untitled", description=None, chapters=chapters)


def fetch_chapter_text(url: str, timeout: int = 30, allow_curl_cffi: bool = True, allow_playwright: bool = False) -> tuple[str, str]:
    page = smart_fetch(url, timeout=timeout, allow_curl_cffi=allow_curl_cffi, allow_playwright=allow_playwright)
    text = parse_chapter_text(page.html)
    return text, page.final_url
