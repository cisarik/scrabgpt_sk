"""Split cached Wikipedia Scrabble HTML into per-language fragments.

The script looks for anchors linking to ``*_language`` pages and captures the
next ``<tbody>`` (and its parent table) after each anchor.  Each fragment is
stored as a standalone HTML file in a ``parsed`` directory that lives beside
``wikipedia_scrabble_cache.html``.
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Iterable, List

from bs4 import BeautifulSoup, Tag


DEFAULT_SOURCE = (
    Path(__file__).resolve().parent.parent
    / "scrabgpt"
    / "assets"
    / "variants"
    / "wikipedia_scrabble_cache.html"
)


def parse_wikipedia_languages(source: Path, output_dir: Path) -> List[Path]:
    """Parse ``source`` and write per-language HTML fragments into ``output_dir``."""
    if not source.exists():
        raise FileNotFoundError(f"Source HTML not found: {source}")

    html = source.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find("div", class_="mw-parser-output")
    if content is None:
        raise ValueError("Could not find main content container 'mw-parser-output'.")

    anchors = [
        anchor
        for anchor in content.find_all("a", href=True)
        if "_language" in anchor["href"] and anchor.find_parent("table") is None
    ]

    output_dir.mkdir(parents=True, exist_ok=True)

    written_paths: List[Path] = []
    seen_tables: set[int] = set()
    missing_tables: list[str] = []

    file_index = 1
    for anchor in anchors:
        tbody = anchor.find_next("tbody")
        if tbody is None:
            missing_tables.append(anchor.get_text(strip=True) or anchor["href"])
            continue

        table: Tag = tbody.find_parent("table") or tbody
        table_identity = id(table)
        if table_identity in seen_tables:
            continue
        seen_tables.add(table_identity)

        fragment = BeautifulSoup(
            "<!DOCTYPE html><html><head><meta charset='utf-8'></head><body></body></html>",
            "html.parser",
        )

        language_name = anchor.get_text(strip=True) or f"Language {file_index}"
        title_tag = fragment.new_tag("title")
        title_tag.string = f"{language_name} Scrabble letter distribution"
        fragment.head.append(title_tag)

        context_node = anchor.find_parent(["h2", "h3", "h4", "p", "li"])
        if context_node is not None:
            fragment.body.append(copy.deepcopy(context_node))
        else:
            fragment.body.append(copy.deepcopy(anchor))

        fragment.body.append(copy.deepcopy(table))

        output_path = output_dir / f"wikipedia_language{file_index}.html"
        output_path.write_text(fragment.prettify(), encoding="utf-8")
        written_paths.append(output_path)
        file_index += 1

    if missing_tables:
        formatted = ", ".join(sorted(set(missing_tables)))
        print(f"Warning: No table found after anchors for: {formatted}")

    return written_paths


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Path to wikipedia_scrabble_cache.html (defaults to repository cache).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where per-language HTML fragments will be stored.",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)
    output_dir = args.output_dir or args.source.parent / "parsed"

    written_paths = parse_wikipedia_languages(args.source, output_dir)
    if written_paths:
        print(f"Wrote {len(written_paths)} fragments to {output_dir}")
    else:
        print("No fragments were written.")


if __name__ == "__main__":
    main()
