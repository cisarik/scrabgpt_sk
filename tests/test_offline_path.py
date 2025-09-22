from __future__ import annotations

from scrabgpt.core.offline_judge import OfflineJudge, should_use_offline_judge


def test_should_use_offline_judge() -> None:
    # enabled=False x loaded=False => False
    assert should_use_offline_judge(False, False) is False
    # enabled=False x loaded=True => False
    assert should_use_offline_judge(False, True) is False
    # enabled=True x loaded=False => False (no silent online without notice)
    assert should_use_offline_judge(True, False) is False
    # enabled=True x loaded=True => True
    assert should_use_offline_judge(True, True) is True


def test_offline_contains_case_and_blank() -> None:
    # In-memory ENABLE subset
    words = {"CATE", "DOG", "HELLO"}
    judge = OfflineJudge(words)

    # Case-insensitive and normalization: lowercase should succeed
    assert judge.contains("cate") is True
    assert judge.contains("CatE") is True
    # Word not in set
    assert judge.contains("CITATE") is False

    # Blank must be expanded before validation; contains should not crash and should return False
    assert judge.contains("C?TE") is False


