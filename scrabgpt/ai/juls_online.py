from __future__ import annotations

import logging

import httpx
from parsel import Selector

log = logging.getLogger("scrabgpt.ai")

# All dictionaries you had in the URL; pass them as a list so httpx renders multiple d= params.
DEFAULT_DICTIONARIES = [
    "kssj4","psp","ogs","sssj","orter","scs","sss","peciar","ssn","hssj",
    "bernolak","noundb","orient","locutio","obce","priezviska","un","onom",
    "pskfr","pskcs","psken",
]

def is_word_in_juls(word: str, *, timeout: float = 10.0) -> bool:
    """Return True iff the JULS search page shows a result (i.e., no <span class="notfound">).
    
    Treats `word` as Unicode. Uses an exact search across DEFAULT_DICTIONARIES.
    Raises httpx.HTTPError on network/HTTP failures (so the caller can decide what to do).
    """
    base_url = "https://slovnik.juls.savba.sk/"
    params = {
        "w": word,          # Unicode ok; httpx will percent-encode & IDNA-encode as needed
        "s": "exact",
        "c": "m5a4",        # any nonce is fine; this is what their UI uses today
        "cs": "",
        "d": DEFAULT_DICTIONARIES,  # multiple d= entries
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (+https://github.com/yourrepo) httpx/2025-demo",
        "Accept-Language": "sk,cs;q=0.9,en;q=0.8",
    }

    try:
        # Follow redirects + HTTP/2 for good measure
        with httpx.Client(http2=True, follow_redirects=True, timeout=timeout, headers=headers) as client:
            r = client.get(base_url, params=params)
            r.raise_for_status()
            sel = Selector(r.text)

            # Primary check: presence of the "notfound" span.
            not_found = bool(sel.css("span.notfound"))

            # Optional hardening: some skins render a localized text; keep as fallback.
            # (Observed text: "Nič nebolo nájdené." on empty results.)
            if not_found:
                return False
            text_snippet = " ".join(sel.css("body ::text").getall()).strip().lower()
            if "nič nebolo nájdené" in text_snippet:
                return False

            return True
    except httpx.HTTPError as e:
        log.warning("JULS online lookup failed for word '%s': %s", word, e)
        raise
    except Exception as e:
        log.warning("Unexpected error during JULS lookup for word '%s': %s", word, e)
        raise
