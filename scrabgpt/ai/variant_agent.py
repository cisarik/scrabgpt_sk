"""Agent that generates per-language Scrabble summaries from Wikipedia cache."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Sequence

from ..core.assets import get_assets_path
from ..core.variant_store import slugify
from .variants import LanguageInfo
from .wiki_loader import (
    LanguageFragment,
    extract_language_fragments,
    fetch_scrabble_html,
)

log = logging.getLogger("scrabgpt.ai.variant_agent")

SUMMARY_DIR = get_assets_path() / "lang_summarizations"


@dataclass
class VariantBootstrapProgress:
    status: str
    language: str | None = None
    detail: str | None = None
    progress_percent: int | None = None
    prompt: str | None = None
    html_snippet_raw: str | None = None
    html_snippet_text: str | None = None
    html_snippet_label: str | None = None


@dataclass
class SummaryResult:
    label: str
    summary: str
    file_path: Path
    language: LanguageInfo


@dataclass
class BootstrapResult:
    summaries: list[SummaryResult]
    languages: list[LanguageInfo]


@dataclass
class TableSnippet:
    label: str
    text: str
    raw_html: str


class VariantBootstrapAgent:
    """Generate human-readable summaries for every Scrabble language fragment."""

    def __init__(self, summary_dir: Path | None = None) -> None:
        self.summary_dir = summary_dir or SUMMARY_DIR
        self.summary_dir.mkdir(parents=True, exist_ok=True)

    async def bootstrap(
        self,
        *,
        on_progress: Callable[[VariantBootstrapProgress], None] | None = None,
        force_refresh: bool = False,
        filter_languages: Sequence[str] | None = None,
    ) -> BootstrapResult:
        def emit(
            status: str,
            *,
            language: str | None = None,
            detail: str | None = None,
            progress_percent: int | None = None,
            html_snippet_raw: str | None = None,
            html_snippet_text: str | None = None,
            html_snippet_label: str | None = None,
        ) -> None:
            if on_progress:
                on_progress(
                    VariantBootstrapProgress(
                        status=status,
                        language=language,
                        detail=detail,
                        progress_percent=progress_percent,
                        html_snippet_raw=html_snippet_raw,
                        html_snippet_text=html_snippet_text,
                        html_snippet_label=html_snippet_label,
                    )
                )

        emit("Načítavam html z Wikipédie...", progress_percent=5)
        html_text = await fetch_scrabble_html(force_refresh=force_refresh)
        fragments = extract_language_fragments(html_text)
        if filter_languages:
            desired = {name.casefold() for name in filter_languages}
            fragments = [fragment for fragment in fragments if fragment.label.casefold() in desired]
        total = len(fragments)

        summaries: list[SummaryResult] = []
        languages: dict[str, LanguageInfo] = {}

        if not fragments:
            emit(
                "Žiadne sekcie nenájdené",
                detail="Wikipedia neposkytla žiadne jazykové rozdelenie",
                progress_percent=100,
            )
            return BootstrapResult(summaries=[], languages=[])

        for idx, fragment in enumerate(fragments, start=1):
            heading = fragment.label

            def _emit(status: str, **kwargs: Any) -> None:
                emit(status, language=heading, **kwargs)

            result = await self._process_fragment(
                fragment,
                fragment_index=idx,
                fragment_total=total,
                emit_func=_emit,
            )
            if result is None:
                continue
            summaries.append(result)
            languages[result.language.name.casefold()] = result.language

        sorted_languages = sorted(languages.values(), key=lambda item: item.name.lower())
        emit(
            "Sumarizácie dokončené",
            detail=f"Vytvorených {len(summaries)} súborov",
            progress_percent=100,
        )
        return BootstrapResult(summaries=summaries, languages=sorted_languages)

    async def generate_language(
        self,
        language_query: str,
        *,
        on_progress: Callable[[VariantBootstrapProgress], None] | None = None,
    ) -> SummaryResult:
        def emit(
            status: str,
            *,
            detail: str | None = None,
            progress_percent: int | None = None,
            html_snippet_raw: str | None = None,
            html_snippet_text: str | None = None,
            html_snippet_label: str | None = None,
        ) -> None:
            if on_progress:
                on_progress(
                    VariantBootstrapProgress(
                        status=status,
                        language=language_query,
                        detail=detail,
                        progress_percent=progress_percent,
                        html_snippet_raw=html_snippet_raw,
                        html_snippet_text=html_snippet_text,
                        html_snippet_label=html_snippet_label,
                    )
                )

        emit("Načítavam HTML pre konkrétny jazyk...", progress_percent=10)
        html_text = await fetch_scrabble_html(force_refresh=False)
        fragments = extract_language_fragments(html_text)
        fragment = next((item for item in fragments if language_query.casefold() in item.label.casefold()), None)
        if fragment is None:
            raise ValueError(f"Sekcia pre jazyk '{language_query}' nebola nájdená.")

        result = await self._process_fragment(
            fragment,
            fragment_index=1,
            fragment_total=1,
            emit_func=emit,
        )
        if result is None:
            raise ValueError(f"Nepodarilo sa vytvoriť sumarizáciu pre jazyk '{language_query}'.")
        return result

    async def _process_fragment(
        self,
        fragment: LanguageFragment,
        *,
        fragment_index: int,
        fragment_total: int,
        emit_func: Callable[..., None],
    ) -> SummaryResult | None:
        tables = self._extract_table_snippets(fragment.body_html, fragment.label)

        def percent(progress_fraction: float) -> int:
            if fragment_total <= 0:
                return 100
            fraction = ((fragment_index - 1) + progress_fraction) / fragment_total
            return max(0, min(100, int(round(fraction * 100))))

        if not tables:
            emit_func(
                status="Sekcia neobsahuje tabuľky",
                detail="Preskakujem jazyk",
                progress_percent=percent(0.0),
            )
            return None

        emit_func(
            status="Našiel som tabuľky",
            detail=f"{len(tables)} tabuliek na spracovanie",
            progress_percent=percent(0.0),
        )

        table_total = len(tables)
        summary_lines: list[str] = []
        if fragment.heading_text:
            summary_lines.append(fragment.heading_text)

        for table_idx, snippet in enumerate(tables, start=1):
            base_fraction = (table_idx - 1) / table_total
            emit_func(
                status="Spracovávam tabuľku",
                detail=f"Tabuľka {table_idx}/{table_total} – {len(snippet.text)} znakov",
                html_snippet_raw=snippet.raw_html,
                html_snippet_text=snippet.text,
                html_snippet_label=snippet.label,
                progress_percent=percent(base_fraction),
            )
            summary_lines.append(f"### {snippet.label}\n{snippet.text}")

        summary_text = "\n\n".join(summary_lines)
        file_path = self._write_summary(fragment, summary_text)

        emit_func(
            status="Fragment spracovaný",
            detail=f"Sumarizácia uložená do {file_path.name}",
            progress_percent=percent(1.0),
        )

        language_info = LanguageInfo(name=fragment.heading_text or fragment.label, code=None)
        return SummaryResult(label=fragment.label, summary=summary_text, file_path=file_path, language=language_info)

    def _write_summary(self, fragment: LanguageFragment, summary_text: str) -> Path:
        slug = slugify(fragment.label) or "language"
        base_path = self.summary_dir / f"summarization_{slug}.txt"
        path = base_path
        suffix = 2
        while path.exists():
            path = self.summary_dir / f"summarization_{slug}_{suffix}.txt"
            suffix += 1
        path.write_text(summary_text, encoding="utf-8")
        return path

    def _extract_table_snippets(self, section_html: str, heading: str) -> list[TableSnippet]:
        cleaned = self._clean_html(section_html)
        tables_html = [table.strip() for table in re.findall(r"<table[^>]*>.*?</table>", cleaned, flags=re.I | re.S)]
        snippets: list[TableSnippet] = []
        for idx, table_html in enumerate(tables_html, start=1):
            parser = _SimpleTableParser()
            parser.feed(table_html)
            label, summary = self._summarise_table(parser, heading, idx)
            if not summary:
                summary = self._fallback_plain_text(table_html)
            raw_preview = table_html[:4000]
            summary_preview = summary[:2000]
            snippets.append(TableSnippet(label=label, text=summary_preview, raw_html=raw_preview))
        return snippets

    def _clean_html(self, html: str) -> str:
        html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
        html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.S | re.I)
        html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.S | re.I)
        return html

    def _summarise_table(self, parser: "_SimpleTableParser", heading: str, index: int) -> tuple[str, str]:
        caption = parser.caption.strip()
        label = caption or f"{heading} – tabuľka {index}"
        rows = parser.rows
        if not rows:
            return label, ""
        header = rows[0]
        header_counts: list[str] = []
        for cell in header[1:]:
            digits = re.findall(r"\d+", cell)
            header_counts.append(digits[0] if digits else cell.strip())
        lines: list[str] = []
        if caption:
            lines.append(f"Caption: {caption}")
        for row in rows[1:]:
            if not row:
                continue
            point_value = row[0].strip()
            if not point_value:
                continue
            entries: list[str] = []
            for idx, cell in enumerate(row[1:]):
                letters = self._split_letters(cell)
                if not letters:
                    continue
                count_label = header_counts[idx] if idx < len(header_counts) else ""
                prefix = f"×{count_label}" if count_label else ""
                entries.append(f"{prefix} {' '.join(letters)}".strip())
            if entries:
                lines.append(f"Points {point_value}: " + "; ".join(entries))
        summary = "\n".join(lines)
        return label, summary

    def _split_letters(self, cell: str) -> list[str]:
        cleaned = re.sub(r"[\n\r\t]+", " ", cell)
        cleaned = re.sub(r"[,;/]+", " ", cleaned)
        tokens = [token.strip() for token in cleaned.split() if token.strip()]
        letters = [token.upper() for token in tokens if token]
        return letters

    def _fallback_plain_text(self, table_html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", table_html)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


class _SimpleTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.caption: str = ""
        self.rows: list[list[str]] = []
        self._tag_stack: list[str] = []
        self._buffer: list[str] = []
        self._current_row: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._tag_stack.append(tag)
        if tag == "caption":
            self._buffer = []
        elif tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"}:
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._tag_stack:
            self._tag_stack.pop()
        if tag == "caption":
            self.caption = "".join(self._buffer).strip()
            self._buffer = []
        elif tag in {"td", "th"}:
            cell_text = "".join(self._buffer).strip()
            if self._current_row is not None:
                self._current_row.append(cell_text)
            self._buffer = []
        elif tag == "tr":
            if self._current_row is not None and any(cell.strip() for cell in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str) -> None:
        if not self._tag_stack:
            return
        current = self._tag_stack[-1]
        if current in {"caption", "td", "th"}:
            self._buffer.append(data)
