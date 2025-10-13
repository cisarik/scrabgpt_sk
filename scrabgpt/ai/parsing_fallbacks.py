"""Helper utilities for AI parsing fallbacks (inline + GPT extraction)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import ValidationError

from .client import OpenAIClient
from .schema import MoveModel, to_move_payload

log = logging.getLogger("scrabgpt.ai.gpt_fallback")


PARSER_ATTEMPTS_BY_METHOD: dict[str, list[str]] = {
    "direct": ["direct"],
    "markdown_extraction": ["direct", "markdown_extraction"],
    "inline_json": ["direct", "markdown_extraction", "inline_json"],
    "gpt_fallback": [
        "direct",
        "markdown_extraction",
        "inline_json",
        "gpt_fallback",
    ],
}


def compute_parser_attempts(method: str) -> list[str]:
    """Return ordered list of parser attempts for the given method."""
    attempts = PARSER_ATTEMPTS_BY_METHOD.get(method)
    if attempts is not None:
        return attempts.copy()
    # Unknown method — include to keep transparency for UI/debugging
    return ["direct", method]


async def gpt_fallback_parse(
    raw_response: str,
    judge_client: OpenAIClient,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Use GPT-5-mini to analyze free-form text and extract a move.

    Returns:
        (move_payload, meta) where move_payload is canonical dict suitable
        for downstream scoring or None if extraction failed. Meta contains:
            - parse_method: always "gpt_fallback"
            - parser_attempts: ordered list of attempts
            - analysis: GPT explanation (string)
            - raw_gpt_response: raw JSON returned by GPT (string)
            - error: optional error description
    """
    meta: dict[str, Any] = {
        "parse_method": "gpt_fallback",
        "parser_attempts": compute_parser_attempts("gpt_fallback"),
        "analysis": "",
        "raw_gpt_response": "",
        "error": "",
    }

    snippet = (raw_response or "").strip()
    if len(snippet) < 32:
        meta["error"] = "GPT fallback preskočený: odpoveď je príliš krátka."
        return None, meta

    prompt = (
        "You are assisting a Scrabble referee system. A model responded with the "
        "following text instead of a clean JSON move description:\n\n"
        f"{snippet[:2000]}\n\n"
        "Analyse this response and reply STRICTLY with JSON that matches this schema:\n"
        "{\n"
        '  "has_move": boolean,\n'
        '  "extracted_move": object | null,\n'
        '  "analysis": string\n'
        "}\n"
        "If you find a valid move, return it as `extracted_move` with placements, start "
        "coordinates, direction, blanks (if any), and word. If no move is present, set "
        "`has_move` to false and explain why in `analysis`. Do not include any extra text."
    )

    def _call_gpt() -> str:
        """Invoke GPT synchronously inside thread executor."""
        max_tokens = min(1200, judge_client.ai_move_max_output_tokens)
        return judge_client._call_text(prompt, max_output_tokens=max_tokens)

    try:
        gpt_text = await asyncio.to_thread(_call_gpt)
    except Exception as exc:  # noqa: BLE001 - propagate reason
        meta["error"] = f"{exc.__class__.__name__}: {exc}"
        log.warning("GPT fallback call failed: %s", exc)
        return None, meta

    meta["raw_gpt_response"] = gpt_text

    try:
        gpt_payload = json.loads(gpt_text)
    except json.JSONDecodeError as decode_err:
        meta["error"] = f"GPT fallback returned non-JSON: {decode_err}"
        log.warning(
            "GPT fallback returned non-JSON (%s). First 200 chars: %s",
            decode_err,
            gpt_text[:200],
        )
        return None, meta

    analysis = gpt_payload.get("analysis")
    if isinstance(analysis, str):
        meta["analysis"] = analysis.strip()

    has_move = gpt_payload.get("has_move")
    extracted = gpt_payload.get("extracted_move")

    if not has_move or not extracted:
        meta["error"] = meta["analysis"] or "GPT fallback nedekódoval žiadny ťah."
        return None, meta

    # Normalise extracted move
    move_data: dict[str, Any] | None
    if isinstance(extracted, str):
        candidate = extracted.strip()
        if not candidate:
            meta["error"] = "GPT fallback: prázdny reťazec pre extrahovaný ťah."
            return None, meta
        try:
            move_data = json.loads(candidate)
        except json.JSONDecodeError as decode_err:
            meta["error"] = f"GPT fallback: JSONDecodeError pri extrahovanom ťahu ({decode_err})."
            log.warning("GPT fallback: invalid JSON string for move: %s", decode_err)
            return None, meta
    elif isinstance(extracted, dict):
        move_data = extracted
    else:
        meta["error"] = (
            "GPT fallback vrátil neznámy typ pre `extracted_move`: "
            f"{type(extracted).__name__}"
        )
        return None, meta

    try:
        move_model = MoveModel.model_validate(move_data)
    except ValidationError as val_err:
        meta["error"] = f"GPT fallback: validácia ťahu zlyhala ({val_err})."
        log.warning("GPT fallback: move validation failed: %s", val_err)
        return None, meta

    move = to_move_payload(move_model)
    if "exchange" not in move:
        move["exchange"] = []

    return move, meta
