from __future__ import annotations

from scrabgpt.ai.client import OpenAIClient


def _run_judge(payload: dict) -> dict:
    class Dummy(OpenAIClient):
        def __init__(self) -> None:
            self.judge_max_output_tokens = 800
            self._slovak_dict = None

        def _call_json(self, prompt, schema, *, max_output_tokens=None):  # type: ignore[override]
            return payload

    return Dummy().judge_words(["OČI"], language="Slovak")


def test_judge_words_accepts_is_playable_flag() -> None:
    payload = {
        "word": "OČI",
        "is_playable": True,
        "reason": "Lexikón to povoľuje.",
        "evidence": [
            "Oficiálny scrabble lexikón (primárne kritérium): OČI je povolené.",
        ],
    }

    result = _run_judge(payload)

    assert result["all_valid"] is True
    assert result["results"] == [
        {
            "word": "OČI",
            "valid": True,
            "reason": (
                "Lexikón to povoľuje."
            ),
        }
    ]


def test_judge_words_accepts_is_playable_inside_results() -> None:
    payload = {
        "results": [
            {
                "word": "OČI",
                "is_playable": True,
                "reason": "Povolené v oficiálnom slovníku.",
            }
        ],
        "all_valid": True,
    }

    result = _run_judge(payload)

    assert result["all_valid"] is True
    assert result["results"][0]["word"] == "OČI"
    assert result["results"][0]["valid"] is True
    assert result["results"][0]["reason"] == "Povolené v oficiálnom slovníku."


def test_judge_words_handles_word_keyed_payload() -> None:
    payload = {
        "VODE": {
            "valid": True,
            "reason": "Platný tvar podstatného mena 'voda'.",
        },
        "DRIEME": {
            "valid": True,
            "reason": "Prítomný čas slovesa 'driemať'.",
        },
    }

    class Dummy(OpenAIClient):
        def __init__(self) -> None:
            self.judge_max_output_tokens = 800
            self._slovak_dict = None

        def _call_json(self, prompt, schema, *, max_output_tokens=None):  # type: ignore[override]
            return payload

    client = Dummy()

    result = client.judge_words(["VODE", "DRIEM"], language="Slovak")

    assert result["all_valid"] is True
    assert {entry["word"] for entry in result["results"]} == {"VODE", "DRIEME"}
    assert all(entry["valid"] for entry in result["results"])
