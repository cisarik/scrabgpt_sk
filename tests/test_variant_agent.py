from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from scrabgpt.ai.variant_agent import SummaryResult, VariantBootstrapAgent
from scrabgpt.ai.wiki_loader import LanguageFragment, extract_language_fragments

WIKIPEDIA_SNIPPET = """
<h3 id="English_(original)">English (original)</h3>
<table><tr><td>dummy</td></tr></table>
<h3 id="Slovak">Slovak</h3>
<table><tr><td>dummy</td></tr></table>
"""


@pytest.mark.asyncio
async def test_generate_language_returns_expected_letters(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def _fetch_html(*_: Any, **__: Any) -> str:  # noqa: D401
        return WIKIPEDIA_SNIPPET

    monkeypatch.setattr("scrabgpt.ai.variant_agent.fetch_scrabble_html", _fetch_html)
    monkeypatch.setattr(
        "scrabgpt.ai.variant_agent.extract_language_fragments",
        lambda _: [
            LanguageFragment(
                label="English",
                body_html="<body><h3>English</h3><table><tbody><tr><th></th><th>×1</th></tr><tr><th>1</th><td>A B</td></tr></tbody></table></body>",
            ),
            LanguageFragment(
                label="Slovak",
                body_html="<body><h3>Slovak</h3><table><tbody><tr><th></th><th>×1</th></tr><tr><th>1</th><td>A Á</td></tr></tbody></table></body>",
            ),
        ],
    )

    agent = VariantBootstrapAgent(summary_dir=tmp_path)
    summary = await agent.generate_language("English")

    assert isinstance(summary, SummaryResult)
    assert summary.language.name == "English"
    assert summary.file_path.exists()
    content = summary.file_path.read_text(encoding="utf-8")
    assert "Points 1" in content
    assert "A B" in content


@pytest.mark.asyncio
async def test_bootstrap_persists_variants_and_languages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def _fetch_html(*_: Any, **__: Any) -> str:
        return WIKIPEDIA_SNIPPET

    monkeypatch.setattr("scrabgpt.ai.variant_agent.fetch_scrabble_html", _fetch_html)
    monkeypatch.setattr(
        "scrabgpt.ai.variant_agent.extract_language_fragments",
        lambda _: [
            LanguageFragment(
                label="English",
                body_html="<body><h3>English</h3><table><tbody><tr><th></th><th>×1</th></tr><tr><th>1</th><td>A B</td></tr></tbody></table></body>",
            ),
            LanguageFragment(
                label="Slovak",
                body_html="<body><h3>Slovak</h3><table><tbody><tr><th></th><th>×1</th></tr><tr><th>1</th><td>A Á</td></tr></tbody></table></body>",
            ),
        ],
    )

    agent = VariantBootstrapAgent(summary_dir=tmp_path)
    result = await agent.bootstrap()

    assert len(result.languages) == 2
    assert len(result.summaries) == 2
    for summary in result.summaries:
        assert summary.file_path.exists()


@pytest.mark.openai
@pytest.mark.asyncio
async def test_bootstrap_real_openai(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    if not os.getenv("RUN_OPENAI_TESTS"):
        pytest.skip("RUN_OPENAI_TESTS not enabled")
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    cache_path = Path(__file__).resolve().parents[1] / "scrabgpt" / "assets" / "variants" / "wikipedia_scrabble_cache.html"
    if not cache_path.exists():
        pytest.skip("wikipedia_scrabble_cache.html missing")

    html = cache_path.read_text(encoding="utf-8")
    fragments = extract_language_fragments(html)
    if not fragments:
        pytest.skip("No fragments extracted")

    subset = fragments[:2]

    async def _fetch_html(*_: Any, **__: Any) -> str:
        return html

    monkeypatch.setattr("scrabgpt.ai.variant_agent.fetch_scrabble_html", _fetch_html)
    monkeypatch.setattr("scrabgpt.ai.variant_agent.extract_language_fragments", lambda _: subset)

    agent = VariantBootstrapAgent(summary_dir=tmp_path)
    result = await agent.bootstrap()

    assert len(result.summaries) == len(subset)
    for summary in result.summaries:
        assert summary.file_path.exists()
