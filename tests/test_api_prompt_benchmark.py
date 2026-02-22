"""Live API benchmark scenarios for prompt-engineering quality checks.

Usage examples:
  OpenAI:
    SCRABGPT_BENCH_MAX_MODELS=2 \
    SCRABGPT_BENCH_SCENARIO_LIMIT=8 \
    poetry run pytest tests/test_api_prompt_benchmark.py::test_openai_api_prompt_benchmark -q -s

  Google:
    SCRABGPT_BENCH_MAX_MODELS=2 \
    SCRABGPT_BENCH_SCENARIO_LIMIT=8 \
    poetry run pytest tests/test_api_prompt_benchmark.py::test_google_api_prompt_benchmark -q -s

Optional strict threshold gate:
  SCRABGPT_BENCH_ASSERT_THRESHOLDS=1

By default, benchmarks print metrics but do not fail on threshold misses,
which keeps runs useful even when provider infra is temporarily unstable.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import pytest

from scrabgpt.ai.mcp_tools import (
    tool_calculate_move_score,
    tool_validate_move_legality,
    tool_validate_word_english,
    tool_validate_word_slovak,
)
from scrabgpt.ai.client import OpenAIClient
from scrabgpt.ai.multi_model import propose_move_multi_model
from scrabgpt.ai.openai_tools_client import OpenAIToolClient
from scrabgpt.ai.tool_adapter import get_gemini_tools, get_openai_tools
from scrabgpt.ai.vertex import VertexClient
from scrabgpt.core.assets import get_premiums_path
from scrabgpt.core.board import BOARD_SIZE, Board
from scrabgpt.core.state import build_ai_state_dict
from scrabgpt.core.variant_store import (
    VariantDefinition,
    get_active_variant_slug,
    load_variant,
    set_active_variant_slug,
)


@dataclass(frozen=True)
class SeedWord:
    word: str
    row: int
    col: int
    direction: str  # "ACROSS" | "DOWN"


@dataclass(frozen=True)
class BenchmarkScenario:
    scenario_id: str
    description: str
    rack: str
    seed_words: tuple[SeedWord, ...] = ()
    variant_slug: str = "english"
    min_score: int = 8
    expect_bingo: bool = False
    expect_blank_use: bool = False
    allow_exchange: bool = False
    tags: frozenset[str] = frozenset()


@dataclass
class ScenarioResult:
    provider: str
    model_id: str
    scenario_id: str
    description: str
    legal: bool
    score: int
    raw_score: int
    bingo: bool
    blank_used: bool
    exchange_or_pass: bool
    leave_quality: float
    quality: float
    success: bool
    elapsed_sec: float
    words: list[str]
    reason: str
    infra_failure: bool
    infra_status: str
    infra_error: str


def _parse_csv_models(raw: str) -> list[str]:
    parsed: list[str] = []
    for item in raw.split(","):
        model = item.strip()
        if not model or model in parsed:
            continue
        parsed.append(model)
    return parsed


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _openai_models_for_benchmark() -> list[str]:
    raw = (
        os.getenv("SCRABGPT_BENCH_OPENAI_MODELS")
        or os.getenv("OPENAI_MODELS")
        or "gpt-5.2"
    )
    models = _parse_csv_models(raw)
    max_models = max(1, _env_int("SCRABGPT_BENCH_MAX_MODELS", 2))
    return models[:max_models]


def _google_models_for_benchmark() -> list[str]:
    raw = (
        os.getenv("SCRABGPT_BENCH_GOOGLE_MODELS")
        or os.getenv("GEMINI_MODELS")
        or os.getenv("GEMINI_MODEL")
        or "gemini-3.1-pro-preview"
    )
    models = _parse_csv_models(raw)
    max_models = max(1, _env_int("SCRABGPT_BENCH_MAX_MODELS", 2))
    return models[:max_models]


def _scenario_catalog() -> list[BenchmarkScenario]:
    # Concrete, repeatable positions covering opening, bingo, blank usage,
    # power-tile scoring, midgame anchors, and tight endgame racks.
    return [
        BenchmarkScenario(
            scenario_id="opening_bingo_balenie",
            description="Prázdna doska, rack má priamy 7-písmenkový bingo ťah.",
            rack="BALENIE",
            variant_slug="slovak",
            min_score=50,
            expect_bingo=True,
            tags=frozenset({"opening", "bingo"}),
        ),
        BenchmarkScenario(
            scenario_id="opening_bingo_blank_balenie",
            description="Prázdna doska, bingo je možné len spotrebovaním blanku.",
            rack="BALENI?",
            variant_slug="slovak",
            min_score=45,
            expect_bingo=True,
            expect_blank_use=True,
            tags=frozenset({"opening", "bingo", "blank"}),
        ),
        BenchmarkScenario(
            scenario_id="opening_bingo_badanie",
            description="Druhá opening bingo pozícia pre stabilitu metriky bingo-rate.",
            rack="BÁDANIE",
            variant_slug="slovak",
            min_score=45,
            expect_bingo=True,
            tags=frozenset({"opening", "bingo"}),
        ),
        BenchmarkScenario(
            scenario_id="mid_pot_taxa_like",
            description="Stred hry s kotvou POŤ; rack z produkčného logu.",
            rack="SAEXAA?",
            seed_words=(SeedWord("POŤ", 7, 6, "ACROSS"),),
            variant_slug="slovak",
            min_score=16,
            tags=frozenset({"midgame", "blank"}),
        ),
        BenchmarkScenario(
            scenario_id="mid_pot_mut_like",
            description="Stred hry s kotvou POŤ; rack LPZKÚÁM z reálneho testu.",
            rack="LPZKÚÁM",
            seed_words=(SeedWord("POŤ", 7, 6, "ACROSS"),),
            variant_slug="slovak",
            min_score=8,
            tags=frozenset({"midgame"}),
        ),
        BenchmarkScenario(
            scenario_id="mid_sam_basa_like",
            description="Kotva SÁM + rack ARBJCAS, očakáva sa legálny skórujúci ťah.",
            rack="ARBJCAS",
            seed_words=(SeedWord("SÁM", 7, 6, "ACROSS"),),
            variant_slug="slovak",
            min_score=12,
            tags=frozenset({"midgame"}),
        ),
        BenchmarkScenario(
            scenario_id="mid_sadia_zo_like",
            description="Kotva SADIA + rack YIEAUZO zo screenshotu.",
            rack="YIEAUZO",
            seed_words=(SeedWord("SADIA", 7, 5, "ACROSS"),),
            variant_slug="slovak",
            min_score=4,
            tags=frozenset({"midgame"}),
        ),
        BenchmarkScenario(
            scenario_id="endgame_exchange_hard",
            description="Ťažký spoluhláskový rack; exchange je prípustný.",
            rack="BCDFGHJ",
            seed_words=(SeedWord("POŤ", 7, 6, "ACROSS"),),
            variant_slug="slovak",
            min_score=0,
            allow_exchange=True,
            tags=frozenset({"endgame", "exchange"}),
        ),
    ]


def _selected_scenarios() -> list[BenchmarkScenario]:
    scenarios = _scenario_catalog()
    filter_ids = _parse_csv_models(os.getenv("SCRABGPT_BENCH_SCENARIOS", ""))
    if filter_ids:
        wanted = set(filter_ids)
        scenarios = [scenario for scenario in scenarios if scenario.scenario_id in wanted]
    max_count = _env_int("SCRABGPT_BENCH_SCENARIO_LIMIT", 6)
    return scenarios[: max(1, max_count)]


def _build_board(seed_words: tuple[SeedWord, ...]) -> Board:
    board = Board(get_premiums_path())
    for seed in seed_words:
        direction = seed.direction.upper()
        if direction not in {"ACROSS", "DOWN"}:
            raise ValueError(f"Unsupported direction: {seed.direction}")
        for idx, ch in enumerate(seed.word.upper()):
            row = seed.row + (idx if direction == "DOWN" else 0)
            col = seed.col + (idx if direction == "ACROSS" else 0)
            if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
                raise ValueError(f"Seed word out of bounds: {seed}")
            cell = board.cells[row][col]
            if cell.letter and cell.letter != ch:
                raise ValueError(
                    f"Seed collision at ({row},{col}): '{cell.letter}' vs '{ch}' in {seed.word}"
                )
            cell.letter = ch
            cell.is_blank = False
            # Existing board letters should not have active premiums in future scoring.
            if cell.premium is not None:
                cell.premium_used = True
    return board


def _compact_state(board: Board, rack: str) -> str:
    st = build_ai_state_dict(board, list(rack), human_score=0, ai_score=0, turn="AI")
    return (
        "grid:\n"
        + "\n".join(st["grid"])
        + f"\nblanks:{st['blanks']}\n"
        + f"ai_rack:{st['ai_rack']}\n"
        + f"scores: H={st['human_score']} AI={st['ai_score']}\n"
        + f"turn:{st['turn']}\n"
    )


def _board_grid(board: Board) -> list[str]:
    rows: list[str] = []
    for r in range(BOARD_SIZE):
        row_chars: list[str] = []
        for c in range(BOARD_SIZE):
            row_chars.append(board.cells[r][c].letter or ".")
        rows.append("".join(row_chars))
    return rows


def _premium_grid(board: Board) -> list[list[dict[str, Any] | None]]:
    grid: list[list[dict[str, Any] | None]] = []
    for r in range(BOARD_SIZE):
        row: list[dict[str, Any] | None] = []
        for c in range(BOARD_SIZE):
            cell = board.cells[r][c]
            if cell.premium is None:
                row.append(None)
                continue
            row.append({"type": cell.premium.name, "used": bool(cell.premium_used)})
        grid.append(row)
    return grid


def _board_is_empty(board: Board) -> bool:
    return not any(board.cells[r][c].letter for r in range(BOARD_SIZE) for c in range(BOARD_SIZE))


def _normalize_placements(move: dict[str, Any]) -> list[dict[str, Any]]:
    raw = move.get("placements")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            row = int(item["row"])
            col = int(item["col"])
            letter = str(item["letter"]).upper()
        except Exception:
            continue
        out.append({"row": row, "col": col, "letter": letter})
    return out


def _consume_rack_with_blanks(rack: str, placements: list[dict[str, Any]]) -> tuple[list[str], bool]:
    pool = list(rack.upper())
    blank_used = False
    for placement in placements:
        letter = str(placement["letter"]).upper()
        if letter in pool:
            pool.remove(letter)
            continue
        if "?" in pool:
            pool.remove("?")
            blank_used = True
            continue
    return pool, blank_used


def _leave_quality(remaining: list[str]) -> float:
    if not remaining:
        return 1.0
    vowels = set("AEIOUYÁÄÉÍÓÔÖÚÜÝ")
    vowel_count = sum(1 for ch in remaining if ch in vowels)
    consonant_count = len(remaining) - vowel_count
    balance_penalty = abs(vowel_count - consonant_count) / max(1, len(remaining))
    diversity = len(set(remaining)) / max(1, len(remaining))
    return max(0.0, 1.0 - balance_penalty) * 0.6 + diversity * 0.4


def _validate_word(language: str, word: str) -> bool:
    if not word:
        return False
    if language.lower().startswith("slovak"):
        result = tool_validate_word_slovak(word)
    else:
        result = tool_validate_word_english(word)
    return bool(result.get("valid"))


class _LocalJudge:
    def judge_words(self, words: list[str], *, language: str) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        all_valid = True
        for word in words:
            valid = _validate_word(language, word)
            if not valid:
                all_valid = False
            results.append(
                {
                    "word": word,
                    "valid": valid,
                    "reason": "local_dictionary" if valid else "not_in_local_dictionary",
                }
            )
        return {"results": results, "all_valid": all_valid}


def _is_infra_failure(status: str, error: str) -> bool:
    status_norm = status.strip().lower()
    error_norm = error.strip().lower()
    if status_norm in {"timeout", "exception"}:
        return True
    if status_norm not in {"ok", "retry", "pending"}:
        infra_markers = (
            "timeout",
            "ssl",
            "connection",
            "network",
            "transport",
            "rate limit",
            "429",
            "500",
            "502",
            "503",
            "504",
            "api",
        )
        return any(marker in error_norm for marker in infra_markers)
    return False


def _evaluate_result(
    *,
    provider: str,
    model_id: str,
    scenario: BenchmarkScenario,
    variant: VariantDefinition,
    board: Board,
    move: dict[str, Any],
    elapsed_sec: float,
    infra_failure: bool,
    infra_status: str,
    infra_error: str,
) -> ScenarioResult:
    placements = _normalize_placements(move)
    exchange_or_pass = bool(move.get("exchange")) or bool(move.get("pass"))
    legal = False
    raw_score = 0
    score = 0
    words: list[str] = []
    reason = ""

    if placements:
        legality = tool_validate_move_legality(
            _board_grid(board),
            placements,
            is_first_move=_board_is_empty(board),
        )
        legal = bool(legality.get("valid"))
        reason = str(legality.get("reason", ""))
        if legal:
            scored = tool_calculate_move_score(
                _board_grid(board),
                _premium_grid(board),
                placements,
            )
            raw_score = int(scored.get("total_score", 0) or 0)
            words_payload = scored.get("words", [])
            if isinstance(words_payload, list):
                for item in words_payload:
                    if not isinstance(item, dict):
                        continue
                    word = str(item.get("word", "")).upper().strip()
                    if word:
                        words.append(word)
            # Word validity is already checked in propose_move_multi_model via judge_client.
    elif exchange_or_pass and scenario.allow_exchange:
        legal = True
        reason = "exchange_or_pass_allowed"
    elif exchange_or_pass:
        legal = True
        reason = "exchange_or_pass_used"
    else:
        reason = "no_move"

    remaining_rack, blank_used = _consume_rack_with_blanks(scenario.rack, placements)
    bingo = len(placements) == 7
    bingo_bonus = 50 if bingo else 0
    score = raw_score + bingo_bonus
    leave_quality = _leave_quality(remaining_rack)

    quality = 0.0
    if legal:
        quality += 0.5
    quality += min(score / 80.0, 1.0)
    quality += leave_quality * 0.25
    if bingo:
        quality += 0.35
    if blank_used:
        quality += 0.20
    if exchange_or_pass and not scenario.allow_exchange:
        quality -= 0.45
    if scenario.expect_bingo and not bingo:
        quality -= 0.40
    if scenario.expect_blank_use and not blank_used:
        quality -= 0.30
    if infra_failure:
        quality -= 0.60

    success = legal
    if not exchange_or_pass and score < scenario.min_score:
        success = False
    if scenario.expect_bingo and not bingo:
        success = False
    if scenario.expect_blank_use and not blank_used:
        success = False
    if exchange_or_pass and not scenario.allow_exchange:
        success = False
    if infra_failure:
        success = False

    return ScenarioResult(
        provider=provider,
        model_id=model_id,
        scenario_id=scenario.scenario_id,
        description=scenario.description,
        legal=legal,
        score=score,
        raw_score=raw_score,
        bingo=bingo,
        blank_used=blank_used,
        exchange_or_pass=exchange_or_pass,
        leave_quality=leave_quality,
        quality=quality,
        success=success,
        elapsed_sec=elapsed_sec,
        words=words,
        reason=reason,
        infra_failure=infra_failure,
        infra_status=infra_status,
        infra_error=infra_error,
    )


def _aggregate(results: list[ScenarioResult], scenarios: list[BenchmarkScenario]) -> dict[str, Any]:
    total = len(results)
    infra_failures = sum(1 for r in results if r.infra_failure)
    completion_rate = (total - infra_failures) / max(1, total)

    eval_pool = [r for r in results if not r.infra_failure]
    if not eval_pool:
        eval_pool = results

    legal_rate = sum(1 for r in eval_pool if r.legal) / max(1, len(eval_pool))
    success_rate = sum(1 for r in eval_pool if r.success) / max(1, len(eval_pool))
    avg_score = sum(r.score for r in eval_pool) / max(1, len(eval_pool))
    avg_quality = sum(r.quality for r in eval_pool) / max(1, len(eval_pool))
    avg_leave_quality = sum(r.leave_quality for r in eval_pool) / max(1, len(eval_pool))
    avg_elapsed = sum(r.elapsed_sec for r in eval_pool) / max(1, len(eval_pool))

    bingo_focus_ids = {s.scenario_id for s in scenarios if s.expect_bingo}
    blank_focus_ids = {s.scenario_id for s in scenarios if s.expect_blank_use}

    bingo_focus = [r for r in eval_pool if r.scenario_id in bingo_focus_ids]
    blank_focus = [r for r in eval_pool if r.scenario_id in blank_focus_ids]

    bingo_rate = sum(1 for r in bingo_focus if r.bingo) / max(1, len(bingo_focus))
    blank_rate = sum(1 for r in blank_focus if r.blank_used) / max(1, len(blank_focus))
    exchange_rate = sum(1 for r in eval_pool if r.exchange_or_pass) / max(1, len(eval_pool))

    return {
        "total_runs": total,
        "infra_failures": infra_failures,
        "completion_rate": completion_rate,
        "evaluated_runs": len(eval_pool),
        "legal_rate": legal_rate,
        "success_rate": success_rate,
        "avg_score": avg_score,
        "avg_quality": avg_quality,
        "avg_leave_quality": avg_leave_quality,
        "avg_elapsed_sec": avg_elapsed,
        "bingo_focus_rate": bingo_rate,
        "blank_focus_rate": blank_rate,
        "exchange_or_pass_rate": exchange_rate,
    }


def _format_report(summary: dict[str, Any], results: list[ScenarioResult]) -> str:
    header = (
        f"runs={summary['total_runs']} "
        f"evaluated={summary['evaluated_runs']} "
        f"completion={summary['completion_rate']:.2%} "
        f"legal={summary['legal_rate']:.2%} "
        f"success={summary['success_rate']:.2%} "
        f"avg_score={summary['avg_score']:.2f} "
        f"avg_quality={summary['avg_quality']:.3f} "
        f"bingo_focus={summary['bingo_focus_rate']:.2%} "
        f"blank_focus={summary['blank_focus_rate']:.2%} "
        f"avg_elapsed={summary['avg_elapsed_sec']:.2f}s"
    )
    lines = [header]
    for run in results:
        lines.append(
            " | ".join(
                [
                    run.model_id,
                    run.scenario_id,
                    f"score={run.score} (raw={run.raw_score})",
                    f"legal={run.legal}",
                    f"bingo={run.bingo}",
                    f"blank={run.blank_used}",
                    f"success={run.success}",
                    f"t={run.elapsed_sec:.2f}s",
                    f"reason={run.reason}",
                    f"infra={run.infra_status}",
                ]
            )
        )
    return "\n".join(lines)


async def _run_provider_benchmark(
    *,
    provider: str,
    model_ids: list[str],
    timeout_seconds: int,
) -> tuple[dict[str, Any], list[ScenarioResult]]:
    scenarios = _selected_scenarios()
    if not scenarios:
        raise RuntimeError("No benchmark scenarios selected")

    previous_slug = get_active_variant_slug()
    use_openai_judge = _env_bool("SCRABGPT_BENCH_USE_OPENAI_JUDGE", False)
    if use_openai_judge and os.getenv("OPENAI_API_KEY"):
        judge: Any = OpenAIClient()
    else:
        judge = _LocalJudge()
    enforce_tool_workflow = _env_bool("SCRABGPT_BENCH_ENFORCE_TOOL_WORKFLOW", False)
    results: list[ScenarioResult] = []

    if provider == "openai":
        client = OpenAIToolClient(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout_seconds=timeout_seconds,
        )
        tools = get_openai_tools()
    elif provider == "google":
        client = VertexClient(
            timeout_seconds=timeout_seconds,
            allow_model_fallback=False,
        )
        tools = get_gemini_tools()
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    try:
        for model_id in model_ids:
            model_info = {"id": model_id, "name": model_id}
            for scenario in scenarios:
                variant = load_variant(scenario.variant_slug)
                set_active_variant_slug(variant.slug)
                board = _build_board(scenario.seed_words)
                compact_state = _compact_state(board, scenario.rack)

                start = time.perf_counter()
                move, _all_results = await propose_move_multi_model(
                    client,  # type: ignore[arg-type]
                    [model_info],
                    compact_state,
                    variant,
                    board,
                    judge,
                    timeout_seconds=timeout_seconds,
                    tools=tools,
                    allow_model_fallback=False,
                    enforce_tool_workflow=enforce_tool_workflow,
                )
                elapsed = time.perf_counter() - start

                infra_status = ""
                infra_error = ""
                infra_failure = False
                if _all_results and isinstance(_all_results[0], dict):
                    primary = _all_results[0]
                    infra_status = str(primary.get("status", ""))
                    infra_error = str(primary.get("error", ""))
                    infra_failure = _is_infra_failure(infra_status, infra_error)

                run = _evaluate_result(
                    provider=provider,
                    model_id=model_id,
                    scenario=scenario,
                    variant=variant,
                    board=board,
                    move=move,
                    elapsed_sec=elapsed,
                    infra_failure=infra_failure,
                    infra_status=infra_status,
                    infra_error=infra_error,
                )
                results.append(run)
    finally:
        set_active_variant_slug(previous_slug)
        await client.close()

    summary = _aggregate(results, scenarios)
    return summary, results


def _assert_benchmark_thresholds(summary: dict[str, Any]) -> None:
    completion_min = _env_float("SCRABGPT_BENCH_COMPLETION_RATE_MIN", 0.50)
    legal_min = _env_float("SCRABGPT_BENCH_LEGAL_RATE_MIN", 0.70)
    success_min = _env_float("SCRABGPT_BENCH_SUCCESS_RATE_MIN", 0.45)
    score_min = _env_float("SCRABGPT_BENCH_AVG_SCORE_MIN", 8.0)
    quality_min = _env_float("SCRABGPT_BENCH_AVG_QUALITY_MIN", 0.55)
    bingo_min = _env_float("SCRABGPT_BENCH_BINGO_RATE_MIN", 0.40)
    blank_min = _env_float("SCRABGPT_BENCH_BLANK_RATE_MIN", 0.40)

    assert summary["completion_rate"] >= completion_min
    assert summary["legal_rate"] >= legal_min
    assert summary["success_rate"] >= success_min
    assert summary["avg_score"] >= score_min
    assert summary["avg_quality"] >= quality_min
    assert summary["bingo_focus_rate"] >= bingo_min
    assert summary["blank_focus_rate"] >= blank_min


def _should_assert_thresholds() -> bool:
    return _env_bool("SCRABGPT_BENCH_ASSERT_THRESHOLDS", False)


@pytest.mark.openai
@pytest.mark.asyncio
async def test_openai_api_prompt_benchmark() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    model_ids = _openai_models_for_benchmark()
    timeout_seconds = max(20, _env_int("SCRABGPT_BENCH_TIMEOUT_SECONDS", 60))
    summary, results = await _run_provider_benchmark(
        provider="openai",
        model_ids=model_ids,
        timeout_seconds=timeout_seconds,
    )
    print("\n[OPENAI BENCHMARK]\n" + _format_report(summary, results))
    if _should_assert_thresholds():
        _assert_benchmark_thresholds(summary)


@pytest.mark.google
@pytest.mark.asyncio
async def test_google_api_prompt_benchmark() -> None:
    model_ids = _google_models_for_benchmark()
    timeout_seconds = max(20, _env_int("SCRABGPT_BENCH_TIMEOUT_SECONDS", 60))
    try:
        summary, results = await _run_provider_benchmark(
            provider="google",
            model_ids=model_ids,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Google benchmark skipped due to configuration/runtime error: {exc}")
        return
    print("\n[GOOGLE BENCHMARK]\n" + _format_report(summary, results))
    if _should_assert_thresholds():
        _assert_benchmark_thresholds(summary)
