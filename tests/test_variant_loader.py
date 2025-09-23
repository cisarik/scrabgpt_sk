from __future__ import annotations

import json
import logging

from scrabgpt.core.variant_store import _load_variant_from_path


def test_load_variant_skips_multichar_letters(tmp_path, caplog):
    payload = {
        "language": "Test",
        "slug": "test",
        "letters": [
            {"letter": "?", "count": 1, "points": 0},
            {"letter": "A", "count": 2, "points": 1},
            {"letter": "CH", "count": 3, "points": 4},
            {"letter": "C", "count": 1, "points": 3},
            {"letter": "H", "count": 1, "points": 2},
        ],
    }
    path = tmp_path / "variant.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    caplog.set_level(logging.WARNING, logger="scrabgpt.variants")
    variant = _load_variant_from_path(path)

    letters = {letter.letter for letter in variant.letters}
    assert "CH" not in letters
    assert {"?", "A", "C", "H"} <= letters

    warnings = [record.message for record in caplog.records]
    assert any("variant_letter_multichar" in msg for msg in warnings)
