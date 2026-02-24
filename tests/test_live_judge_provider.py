"""Live judge-provider integration test for one concrete Slovak word.

This test performs a real LLM API call and is intentionally opt-in.
Run it explicitly with:

    RUN_LIVE_JUDGE_TESTS=true poetry run pytest tests/test_live_judge_provider.py -q -s
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import pytest

from scrabgpt.ai.client import JudgeBatchResponse, JudgeResult, OpenAIClient
from scrabgpt.ai.vertex import VertexClient
from scrabgpt.core.opponent_mode import OpponentMode

TARGET_WORD = "paralelizácia"
TARGET_LANGUAGE = "Slovak"


def _resolve_judge_provider() -> OpponentMode:
    raw = (os.getenv("JUDGE_PROVIDER") or "").strip()
    if raw:
        try:
            mode = OpponentMode.from_string(raw)
            if mode in {OpponentMode.BEST_MODEL, OpponentMode.GEMINI}:
                return mode
        except ValueError:
            pass
    return OpponentMode.BEST_MODEL


def _resolve_openai_model() -> str:
    configured = (os.getenv("JUDGE_OPENAI_MODEL") or "").strip()
    if configured:
        return configured
    for item in (os.getenv("OPENAI_MODELS") or "").split(","):
        model_id = item.strip()
        if model_id:
            return model_id
    return "gpt-5.2"


def _resolve_gemini_model() -> str:
    for env_key in (
        "JUDGE_GEMINI_MODEL",
        "GEMINI_MODEL",
        "GOOGLE_GEMINI_MODEL",
    ):
        model_id = (os.getenv(env_key) or "").strip()
        if model_id:
            return model_id
    return "gemini-2.5-pro"


def _resolve_judge_tokens() -> int:
    raw = os.getenv("JUDGE_MAX_OUTPUT_TOKENS", "800")
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 800
    return max(200, min(parsed, 1200))


def _extract_json_from_content(content: str) -> Any:
    text = content.strip()
    if not text:
        raise ValueError("Model returned empty response content.")

    if text.startswith("```"):
        lines = [
            line
            for line in text.splitlines()
            if not line.strip().startswith("```")
        ]
        text = "\n".join(lines).strip()

    candidates: list[str] = [text]
    obj_start = text.find("{")
    obj_end = text.rfind("}")
    if obj_start >= 0 and obj_end > obj_start:
        candidates.append(text[obj_start:obj_end + 1].strip())
    arr_start = text.find("[")
    arr_end = text.rfind("]")
    if arr_start >= 0 and arr_end > arr_start:
        candidates.append(text[arr_start:arr_end + 1].strip())

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("Model response did not contain valid JSON.")


def _find_target_result(result: JudgeBatchResponse) -> JudgeResult:
    entries = result.get("results", [])
    for entry in entries:
        if str(entry.get("word", "")).casefold() == TARGET_WORD.casefold():
            return entry
    if len(entries) == 1:
        return entries[0]
    raise AssertionError(f"Target word '{TARGET_WORD}' not found in judge response: {entries}")


def _is_live_provider_config_issue(error_text: str) -> bool:
    lowered = error_text.lower()
    markers = (
        "insufficient_quota",
        "exceeded your current quota",
        "billing",
        "rate limit",
        "429",
        "permission denied",
        "forbidden",
        "authentication",
        "credentials",
        "api key",
    )
    return any(marker in lowered for marker in markers)


async def _judge_with_gemini_live(model_id: str, max_tokens: int) -> JudgeBatchResponse:
    prompt = OpenAIClient.build_judge_prompt([TARGET_WORD], TARGET_LANGUAGE)
    schema_json = json.dumps(OpenAIClient.judge_schema(), ensure_ascii=False)
    prompt_with_schema = (
        f"{prompt}\n"
        f"Return ONLY strict JSON matching this schema:\n{schema_json}\n"
        "Do not include markdown or commentary."
    )

    client = VertexClient(timeout_seconds=60, allow_model_fallback=False)
    try:
        response = await client.call_model(
            model_id,
            prompt=prompt_with_schema,
            max_tokens=max_tokens,
            thinking_mode=False,
            tools=[],
            request_timeout_seconds=60,
        )
    finally:
        await client.close()

    if str(response.get("status") or "").lower() != "ok":
        raise RuntimeError(f"Gemini judge call failed: {response.get('error')}")

    content = str(response.get("content") or "").strip()
    payload = _extract_json_from_content(content)
    return OpenAIClient.normalize_judge_payload(payload, [TARGET_WORD])


@pytest.mark.network
def test_live_judge_validates_paralelizacia_with_configured_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.getenv("RUN_LIVE_JUDGE_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        pytest.skip("Set RUN_LIVE_JUDGE_TESTS=true to run paid live judge integration test.")

    provider = _resolve_judge_provider()
    max_tokens = _resolve_judge_tokens()

    if provider == OpponentMode.BEST_MODEL:
        if not os.getenv("OPENAI_API_KEY", "").strip():
            pytest.skip("OPENAI_API_KEY is not configured.")
        model_id = _resolve_openai_model()
        # OpenAIClient resolves primary model from OPENAI_MODELS; pin it to judge model for this test.
        monkeypatch.setenv("OPENAI_MODELS", model_id)
        client = OpenAIClient(model=model_id)
        # Force direct LLM path for Slovak (skip local dictionary/JULS tiers).
        client._slovak_dict = None
        client.judge_max_output_tokens = max_tokens
        try:
            result = client.judge_words([TARGET_WORD], language=TARGET_LANGUAGE)
        except Exception as exc:  # noqa: BLE001
            if _is_live_provider_config_issue(str(exc)):
                pytest.skip(f"OpenAI live judge test skipped due to provider/config issue: {exc}")
            raise
    elif provider == OpponentMode.GEMINI:
        model_id = _resolve_gemini_model()
        try:
            result = asyncio.run(_judge_with_gemini_live(model_id, max_tokens))
        except Exception as exc:  # noqa: BLE001
            if _is_live_provider_config_issue(str(exc)):
                pytest.skip(f"Gemini live judge test skipped due to provider/config issue: {exc}")
            raise
    else:
        pytest.skip(f"Unsupported JUDGE_PROVIDER for live judge test: {provider.value}")

    entry = _find_target_result(result)
    assert entry["word"].casefold() == TARGET_WORD.casefold()
    assert entry["reason"].strip()
    assert entry["valid"] is True, (
        f"Expected '{TARGET_WORD}' to be valid, got valid={entry['valid']} reason={entry['reason']}"
    )
    assert result["all_valid"] is True
