from __future__ import annotations

from pathlib import Path

import pytest

from scrabgpt.ai.multi_model import propose_move_multi_model
from scrabgpt.ai.novita_multi_model import propose_move_novita_multi_model
from scrabgpt.core.board import Board
from scrabgpt.core.variant_store import VariantDefinition


PREMIUMS_PATH = Path("scrabgpt/assets/premiums.json")


class _ErroringClient:
    ai_move_max_output_tokens = 800

    async def call_model(self, model_id: str, prompt: str, max_tokens: int | None = None) -> dict[str, object]:
        return {
            "status": "error",
            "error": "Simulated failure",
            "model": model_id,
            "content": "",
            "raw_json": {},
            "trace_id": "trace",
            "call_id": "call",
            "elapsed": 0.1,
            "timeout_seconds": 30,
            "request_payload": {},
            "request_headers": {},
            "response_headers": {},
        }

    async def close(self) -> None:
        return None


class _StubJudge:
    ai_move_max_output_tokens = 800

    def judge_words(self, words: list[str], *, language: str) -> dict[str, object]:
        return {"results": [], "all_valid": False}


def _make_board() -> Board:
    return Board(str(PREMIUMS_PATH))


def _make_variant() -> VariantDefinition:
    return VariantDefinition(slug="test", language="Slovak", letters=tuple())


@pytest.mark.asyncio
async def test_openrouter_multi_model_returns_pass_on_all_errors() -> None:
    client = _ErroringClient()
    judge = _StubJudge()
    models = [{"id": "m1", "name": "Model 1"}, {"id": "m2", "name": "Model 2"}]
    move, results = await propose_move_multi_model(
        client,
        models,
        compact_state="state",
        variant=_make_variant(),
        board=_make_board(),
        judge_client=judge,
    )

    assert move.get("pass") is True
    assert move.get("placements") == []
    assert move.get("exchange") == []
    reason = str(move.get("reason", ""))
    assert reason
    assert "Model 1" in reason
    assert "Simulated failure" in reason
    assert len(results) == len(models)
    assert all(r.get("status") != "ok" for r in results)


@pytest.mark.asyncio
async def test_novita_multi_model_returns_pass_on_all_errors() -> None:
    client = _ErroringClient()
    judge = _StubJudge()
    models = [{"id": "n1", "name": "Novita 1"}]
    move, results = await propose_move_novita_multi_model(
        client,
        models,
        compact_state="state",
        variant=_make_variant(),
        board=_make_board(),
        judge_client=judge,
    )

    assert move.get("pass") is True
    assert move.get("placements") == []
    assert move.get("exchange") == []
    reason = str(move.get("reason", ""))
    assert reason
    assert "Novita 1" in reason
    assert "Simulated failure" in reason
    assert len(results) == len(models)
    assert all(r.get("status") != "ok" for r in results)
