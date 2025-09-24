from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup
from openai import OpenAI
from openai import APIStatusError

JULS_BASE = "https://slovnik.juls.savba.sk/"
JULS_PARAMS = (
    "s=exact&c=k546&cs=&d=kssj4&d=psp&d=ogs&d=sssj&d=orter&d=scs&d=sss&d=peciar"
    "&d=ssn&d=hssj&d=bernolak&d=noundb&d=orient&d=locutio&d=obce&d=priezviska"
    "&d=un&d=onom&d=pskfr&d=pskcs&d=psken"
)
UA = "Mozilla/5.0 (compatible; JulsChecker/1.0; +https://example.com/contact)"


# -----------------------------
# Nízkourovňové volanie na JÚĽŠ
# -----------------------------


@dataclass
class JulsHttp:
    url: str
    status: int
    html: str


def _request_juls(word: str, timeout_s: float = 15.0, retries: int = 2, backoff_s: float = 0.8) -> JulsHttp:
    base_params = urllib.parse.parse_qsl(JULS_PARAMS, keep_blank_values=True)
    params = [("w", word)] + base_params
    q = urllib.parse.urlencode(params, doseq=True)
    url = f"{JULS_BASE}?{q}"
    headers = {
        "User-Agent": UA,
        "Accept-Language": "sk,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml",
    }
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=timeout_s,
                headers=headers,
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                return JulsHttp(url=url, status=resp.status_code, html=resp.text)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff_s * (2**attempt))
            else:
                raise
    raise RuntimeError(str(last_exc))


# ---------------------------------
# Parsovanie výsledkov zo stránky
# ---------------------------------


@dataclass
class MatchItem:
    dictionary: str
    headword: str
    url: str
    quote: Optional[str] = None


def _clean_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clip(text: str, limit: int = 160) -> str:
    text = _clean_space(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def parse_juls_results(html_text: str, base_url: str, query_word: str) -> List[MatchItem]:
    soup = BeautifulSoup(html_text, "html.parser")
    items: List[MatchItem] = []

    for section in soup.select("section[id^=qb_]"):
        section_id = section.get("id", "")
        if not section_id.startswith("qb_"):
            continue
        dictionary = section_id[3:].strip() or "?"
        for body in section.select(".resultbody"):
            body_text = _clip(body.get_text(" ", strip=True), 200)
            headword = ""
            bw = body.find("b") or body.find("strong") or body.find("em")
            if bw is not None:
                headword = _clean_space(bw.get_text(" ").strip())
            if not headword:
                headword = query_word
            url_params = urllib.parse.urlencode(
                {
                    "w": headword,
                    "s": "exact",
                    "d": dictionary,
                }
            )
            url = urllib.parse.urljoin(base_url, f"?{url_params}")
            items.append(
                MatchItem(
                    dictionary=dictionary,
                    headword=headword,
                    url=url,
                    quote=body_text,
                )
            )

    seen: set[tuple[str, str]] = set()
    unique: List[MatchItem] = []
    for item in items:
        key = (item.dictionary, item.headword.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


# ---------------------------------
# Nástroj pre „agent tool-calling“
# ---------------------------------


def tool_lookup_juls(word: str) -> Dict[str, Any]:
    http = _request_juls(word)
    matches = [
        vars(match)
        for match in parse_juls_results(http.html, base_url=JULS_BASE, query_word=word)
    ]
    return {
        "query": word,
        "source_url": http.url,
        "http_status": http.status,
        "matches": matches,
    }


# ---------------------------------
# OpenAI agent s JSON Schema výstupom
# ---------------------------------


JSON_SCHEMA = {
    "name": "JulsWordValidation",
    "schema": {
        "type": "object",
        "properties": {
            "valid": {
                "type": "boolean",
                "description": "Je slovo platné (našlo sa aspoň v jednom slovníku JÚĽŠ)?",
            },
            "reasoning": {
                "type": "string",
                "description": (
                    "Krátka, vecná obhajoba v slovenčine: prečo je/nie je slovo platné, "
                    "s odkazom na konkrétne slovníky."
                ),
            },
            "evidence": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "source_url": {"type": "string"},
                    "http_status": {"type": "integer"},
                    "matches": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "dictionary": {
                                    "type": "string",
                                    "description": "Kód slovníka (napr. kssj, sssp, psp...).",
                                },
                                "headword": {"type": "string"},
                                "url": {"type": "string"},
                                "quote": {
                                    "type": "string",
                                    "description": "Krátka citácia z okolia nálezu (≤ ~180 znakov).",
                                },
                            },
                            "required": ["dictionary", "headword", "url"],
                        },
                    },
                },
                "required": ["query", "source_url", "http_status", "matches"],
            },
        },
        "required": ["valid", "reasoning", "evidence"],
        "additionalProperties": False,
    },
    "strict": True,
}


SYSTEM_PROMPT = (
    "Si presný lexikálny validátor pre slovenčinu. "
    "Dostaneš surové dôkazy z portálu JÚĽŠ (slovnik.juls.savba.sk). "
    "Vráť JSON podľa danej JSON schémy: rozhodni 'valid' na základe toho, či existuje aspoň jeden zápis. "
    "Do 'reasoning' urob stručnú obhajobu v slovenčine a pripomeň, v ktorých slovníkoch sa našiel záznam. "
    "Citácie dávaj len krátke (do ~1–2 viet) a neprekračuj férové použitie."
)


def _call_agent_json(
    system_prompt: str,
    user_content: str,
    *,
    schema: dict[str, Any],
    client: OpenAI,
    model: str,
) -> str:
    try:
        resp = client.responses.create(  # type: ignore[call-overload]
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": schema,
            },
        )
        return resp.output_text
    except TypeError as exc:
        # staršie SDK nepodporujú response_format pre Responses API
        try:
            chat = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": (
                            user_content
                            + "\n\nOdpovedz striktne ako JSON zodpovedajúci poskytnutej schéme; žiadny ďalší text."
                        ),
                    },
                ],
            )
            content = chat.choices[0].message.content or ""
            return content
        except Exception as inner_exc:  # noqa: BLE001
            raise RuntimeError(f"JÚĽŠ agent zlyhal: {inner_exc}") from exc


def agent_validate_word(word: str, *, openai_api_key: str) -> Dict[str, Any]:
    client = OpenAI(api_key=openai_api_key)
    evidence = tool_lookup_juls(word)
    model = os.getenv("JULS_AGENT_MODEL", "gpt-5-mini")
    user_content = (
        "Over platnosť slova a priprav odôvodnenie. "
        "Použi len tieto dôkazy:\n\n"
        + json.dumps(evidence, ensure_ascii=False, indent=2)
    )
    try:
        content = _call_agent_json(
            SYSTEM_PROMPT,
            user_content,
            schema=JSON_SCHEMA,
            client=client,
            model=model,
        )
    except APIStatusError as exc:
        raise RuntimeError(f"JÚĽŠ agent zlyhal: {exc.message}") from exc
    if not content:
        raise RuntimeError("JÚĽŠ agent nevrátil žiadnu odpoveď.")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JÚĽŠ agent poskytol neplatný JSON: {content}") from exc


def plain_validate_word(word: str) -> dict[str, Any]:
    evidence = tool_lookup_juls(word)
    matches = evidence.get("matches")
    valid = bool(matches)
    quote = ""
    if isinstance(matches, list):
        for item in matches:
            if isinstance(item, dict):
                candidate = item.get("quote")
                if isinstance(candidate, str) and candidate.strip():
                    quote = candidate.strip()
                    break
    return {
        "valid": valid,
        "quote": quote,
        "evidence": evidence,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Použitie: python juls_agent.py <slovo>")
        raise SystemExit(2)

    word_arg = sys.argv[1]
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY nie je nastavený.")

    result = agent_validate_word(word_arg, openai_api_key=api_key)
    print(json.dumps(result, ensure_ascii=False, indent=2))
