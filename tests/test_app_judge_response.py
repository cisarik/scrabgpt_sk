from scrabgpt.ui.app import MainWindow


def test_analyze_judge_response_handles_word_map() -> None:
    response = {
        "LETO": {
            "valid": True,
            "reason": "ok",
        },
        "TO": {
            "valid": True,
            "reason": "ok",
        },
    }

    all_valid, entries = MainWindow._analyze_judge_response(response)

    assert all_valid is True
    assert {entry["word"] for entry in entries} == {"LETO", "TO"}
    assert all(entry.get("valid") for entry in entries)


def test_analyze_judge_response_detects_invalid_in_word_map() -> None:
    response = {
        "LETO": {
            "valid": True,
            "reason": "ok",
        },
        "XYZ": {
            "valid": False,
            "reason": "nope",
        },
    }

    all_valid, entries = MainWindow._analyze_judge_response(response)

    assert all_valid is False
    assert any(entry["word"] == "XYZ" and not entry.get("valid") for entry in entries)
