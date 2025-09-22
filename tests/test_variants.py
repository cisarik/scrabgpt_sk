from __future__ import annotations

from scrabgpt.ai.variants import fetch_variant_definition


SLOVAK_VARIANT_PAYLOAD = {
    "language": "Slovak",
    "code": "sk",
    "letters": [
        {"letter": "?", "count": 2, "points": 0},
        {"letter": "O", "count": 10, "points": 1},
        {"letter": "A", "count": 9, "points": 1},
        {"letter": "E", "count": 8, "points": 1},
        {"letter": "I", "count": 6, "points": 1},
        {"letter": "N", "count": 5, "points": 1},
        {"letter": "S", "count": 5, "points": 1},
        {"letter": "V", "count": 5, "points": 1},
        {"letter": "T", "count": 4, "points": 1},
        {"letter": "R", "count": 5, "points": 2},
        {"letter": "K", "count": 4, "points": 2},
        {"letter": "L", "count": 4, "points": 2},
        {"letter": "D", "count": 3, "points": 3},
        {"letter": "M", "count": 3, "points": 3},
        {"letter": "P", "count": 3, "points": 3},
        {"letter": "U", "count": 3, "points": 3},
        {"letter": "B", "count": 2, "points": 2},
        {"letter": "J", "count": 2, "points": 2},
        {"letter": "Y", "count": 2, "points": 2},
        {"letter": "Z", "count": 2, "points": 2},
        {"letter": "Á", "count": 2, "points": 2},
        {"letter": "C", "count": 1, "points": 3},
        {"letter": "H", "count": 1, "points": 3},
        {"letter": "É", "count": 1, "points": 3},
        {"letter": "Í", "count": 1, "points": 3},
        {"letter": "Ú", "count": 1, "points": 3},
        {"letter": "Ý", "count": 1, "points": 3},
        {"letter": "Č", "count": 1, "points": 3},
        {"letter": "Š", "count": 1, "points": 3},
        {"letter": "Ž", "count": 1, "points": 3},
        {"letter": "Ť", "count": 1, "points": 4},
        {"letter": "Ľ", "count": 1, "points": 5},
        {"letter": "Ô", "count": 1, "points": 7},
        {"letter": "Ň", "count": 1, "points": 7},
        {"letter": "Ä", "count": 1, "points": 8},
        {"letter": "Ó", "count": 1, "points": 8},
        {"letter": "Ď", "count": 1, "points": 8},
        {"letter": "Ĺ", "count": 1, "points": 10},
        {"letter": "Ŕ", "count": 1, "points": 10},
        {"letter": "X", "count": 1, "points": 10},
    ],
}


class _StubClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.schema = None
        self.prompt = ""

    def _call_json(self, prompt, schema, **_: object):  # noqa: ANN001
        self.prompt = prompt
        self.schema = schema
        return self.payload


def test_fetch_variant_definition_slovak() -> None:
    stub = _StubClient(SLOVAK_VARIANT_PAYLOAD)
    definition = fetch_variant_definition(stub, language_request="Slovenský Scrabble variant", iso_code="sk")

    assert definition.language == "Slovak"
    assert definition.slug == "slovak"
    assert definition.source == "openai[sk]"
    assert definition.tile_points["?"] == 0
    assert definition.tile_points["Ň"] == 7
    assert definition.distribution["Á"] == 2
    assert definition.distribution["?"] == 2
    assert definition.total_tiles == 108
