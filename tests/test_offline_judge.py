from __future__ import annotations

from pathlib import Path
import tempfile

from scrabgpt.core.offline_judge import OfflineJudge


def test_offline_judge_contains_basic():
    # vytvor docasny maly wordlist
    content = "\n".join([
        "cat",
        "AX",
        "Dog",
        "",
        "# comment",
    ])
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "list.txt"
        p.write_text(content, encoding="utf-8")
        judge = OfflineJudge.from_path(str(p))
        # case-insensitive a normalizacia na A–Z
        assert judge.contains("CAT") is True
        assert judge.contains("cat") is True
        assert judge.contains("Dog") is True
        assert judge.contains("dog") is True
        # slovo, ktore nie je v zozname
        assert judge.contains("CATS") is False


def test_offline_judge_blank_already_resolved():
    # Simulacia: blank je rozvinuty pred validaciou, tu testujeme len obsah
    content = "CAT\nAX\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "list.txt"
        p.write_text(content, encoding="utf-8")
        judge = OfflineJudge.from_path(str(p))
        # "?" sa nema posielat; namiesto toho uz rozvinute slovo
        assert judge.contains("CAT") is True
        assert judge.contains("AX") is True
        assert judge.contains("A?X") is False  # neočakávame nerozvinuté blanky


def test_offline_judge_count_changes_after_rewrite(tmp_path):
    p = tmp_path / "list.txt"
    p.write_text("CAT\nAX\nDOG\n", encoding="utf-8")
    judge = OfflineJudge.from_path(str(p))
    assert judge.count() == 3
    # prepíš obsah (pridaj nové slová, odstráň staré)
    p.write_text("ONLY\nONE\n", encoding="utf-8")
    judge2 = OfflineJudge.from_path(str(p))
    assert judge2.count() == 2


