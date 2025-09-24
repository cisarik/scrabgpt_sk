import os
from pathlib import Path

import pytest

from scrabgpt.ai.juls_agent import JULS_BASE, parse_juls_results, plain_validate_word

DATA_DIR = Path(__file__).parent / "data"


def test_parse_juls_results_ex_contains_citation() -> None:
    html = (DATA_DIR / "juls_ex.html").read_text(encoding="utf-8")
    matches = parse_juls_results(html, base_url=JULS_BASE, query_word="ex")
    assert matches, "očakáva sa aspoň jeden výsledok"
    dictionaries = {item.dictionary for item in matches}
    assert "kssj4" in dictionaries
    assert "psp" in dictionaries
    first = matches[0]
    assert "vypiť na ex" in (first.quote or "")


def test_plain_validate_word_returns_quote_and_valid() -> None:
    html = (DATA_DIR / "juls_ex.html").read_text(encoding="utf-8")
    # Patch tool_lookup_juls to avoid network by monkeypatch-style manual injection
    from scrabgpt.ai import juls_agent

    def fake_lookup(word: str) -> dict[str, object]:  # type: ignore[override]
        assert word == "ex"
        return {
            "query": word,
            "source_url": "https://example" ,
            "http_status": 200,
            "matches": [vars(match) for match in parse_juls_results(html, JULS_BASE, word)],
        }

    original_lookup = juls_agent.tool_lookup_juls
    try:
        juls_agent.tool_lookup_juls = fake_lookup  # type: ignore[assignment]
        payload = plain_validate_word("ex")
    finally:
        juls_agent.tool_lookup_juls = original_lookup  # type: ignore[assignment]

    assert payload["valid"] is True
    assert "vypiť na ex" in payload["quote"]


@pytest.mark.network
@pytest.mark.skipif(
    os.getenv("SKIP_NETWORK_TESTS") == "1",
    reason="Network tests disabled",
)
def test_plain_validate_word_live_ex() -> None:
    payload = plain_validate_word("ex")
    assert payload["valid"] is True
    assert "vypiť" in payload["quote"].lower()
