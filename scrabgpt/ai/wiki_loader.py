"""Utilities for downloading and splitting Wikipedia Scrabble distribution data."""

from __future__ import annotations

import asyncio
import copy
import html
import logging
import re
import time
from dataclasses import dataclass
from typing import Dict, List

import httpx
from bs4 import BeautifulSoup

from ..core.assets import get_assets_path

log = logging.getLogger("scrabgpt.ai.wiki_loader")


_CACHE_DIR = get_assets_path() / "variants"
_CACHE_FILE = _CACHE_DIR / "wikipedia_scrabble_cache.html"
_CACHE_LOCK = asyncio.Lock()
_CACHE_TTL_SECONDS = 6 * 3600  # refresh every 6 hours by default

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/Scrabble_letter_distributions"
HTTP_HEADERS = {
    "User-Agent": "ScrabGPT-Agent/1.0 (+https://github.com/cisarik/scrabgpt_sk)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


async def fetch_scrabble_html(force_refresh: bool = False) -> str:
    """Download the Scrabble letter distribution Wikipedia page with caching."""

    async with _CACHE_LOCK:
        if not force_refresh and _CACHE_FILE.exists():
            age = time.time() - _CACHE_FILE.stat().st_mtime
            if age < _CACHE_TTL_SECONDS:
                try:
                    return _CACHE_FILE.read_text(encoding="utf-8")
                except Exception as exc:  # noqa: BLE001
                    log.warning("wiki_cache_read_failed path=%s error=%s", _CACHE_FILE, exc)

        log.info("wiki_fetch_start url=%s", WIKIPEDIA_URL)
        async with httpx.AsyncClient(headers=HTTP_HEADERS, timeout=20.0) as client:
            response = await client.get(WIKIPEDIA_URL)
            response.raise_for_status()
            html_text = response.text

        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _CACHE_FILE.write_text(html_text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("wiki_cache_write_failed path=%s error=%s", _CACHE_FILE, exc)

        return html_text


def split_language_sections(html_body: str) -> Dict[str, str]:
    """Split the Wikipedia article into sections keyed by language heading."""

    sections: Dict[str, str] = {}

    heading_pattern = re.compile(r"<h(2|3) id=\"([^\"]+)\">(.*?)</h\1>", re.I | re.S)
    matches = list(heading_pattern.finditer(html_body))
    for idx, match in enumerate(matches):
        level = match.group(1)
        heading_html = match.group(3)
        heading_text = html.unescape(re.sub(r"<.*?>", " ", heading_html)).strip()

        # Only consider headings that look like language names (skip appendix etc.)
        if not heading_text:
            continue
        if level == "2" and """Distribution""" not in heading_text and "Scrabble" not in heading_text:
            # h2 sections like "European languages" are grouping-only; skip
            continue

        # Determine section end
        section_start = match.end()
        if idx + 1 < len(matches):
            section_end = matches[idx + 1].start()
        else:
            section_end = len(html_body)
        section_html = html_body[section_start:section_end]

        sections[heading_text] = section_html

    return sections


@dataclass
class LanguageFragment:
    label: str
    body_html: str
    heading_text: str | None = None


def extract_language_fragments(html_body: str) -> List[LanguageFragment]:
    """Extract cleaned per-language HTML fragments suitable for LLM processing."""

    soup = BeautifulSoup(html_body, "html.parser")
    content = soup.find("div", class_="mw-parser-output")
    if content is None:
        return []

    fragments: list[LanguageFragment] = []
    seen_tables: set[int] = set()

    anchors = [
        anchor
        for anchor in content.find_all("a", href=True)
        if "_language" in anchor["href"] and anchor.find_parent("table") is None
    ]

    for anchor in anchors:
        tbody = anchor.find_next("tbody")
        if tbody is None:
            continue

        table = tbody.find_parent("table") or tbody
        identity = id(table)
        if identity in seen_tables:
            continue
        seen_tables.add(identity)

        label = anchor.get_text(strip=True) or anchor["href"]
        heading = anchor.find_previous(["h2", "h3", "h4"]) or anchor

        fragment_soup = BeautifulSoup(
            "<!DOCTYPE html><html><head><meta charset='utf-8'></head><body></body></html>",
            "html.parser",
        )
        fragment_body = fragment_soup.body
        fragment_body.append(copy.deepcopy(heading))
        fragment_body.append(copy.deepcopy(table))

        # Only keep body inner HTML
        body_html = fragment_body.decode()
        fragments.append(
            LanguageFragment(
                label=label,
                body_html=body_html,
                heading_text=heading.get_text(strip=True) if heading else None,
            )
        )

    return fragments
