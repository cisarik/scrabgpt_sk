from __future__ import annotations

import json
import logging
import os
from typing import Any, TypedDict, cast

from dotenv import load_dotenv
from openai import OpenAI

log = logging.getLogger("scrabgpt.ai")

# Pozn.: Pouzivame Responses API s json_schema formatom (strict JSON vystup).

class JudgeResult(TypedDict):
    word: str
    valid: bool
    reason: str

class JudgeBatchResponse(TypedDict):
    results: list[JudgeResult]
    all_valid: bool

class MoveProposal(TypedDict):
    placements: list[dict[str, int | str]]
    direction: str
    word: str
    exchange: list[str]
    pass_: bool

def _mask_key(k: str) -> str:
    if not k:
        return ""
    if len(k) <= 8:
        return "****"
    return k[:4] + "..." + k[-4:]

class OpenAIClient:
    """Tenký klient s logovaním request/response a maskovaním API kluca."""
    def __init__(self, model: str = "gpt-5-mini") -> None:
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY", "")
        self.client = OpenAI(api_key=api_key if api_key else None)
        self.model = model
        log.info("OpenAI client init (model=%s, key=%s)", model, _mask_key(api_key))
        # Bezpecnost: nikdy neloguj obsah .env ani plny kluc.

        # Limity vystupu (ochrana rozpoctu). Možno upraviť v .env
        self.ai_move_max_output_tokens: int = int(os.getenv("AI_MOVE_MAX_OUTPUT_TOKENS", "3600"))
        self.judge_max_output_tokens: int = int(os.getenv("JUDGE_MAX_OUTPUT_TOKENS", "800"))

    def _call_json(
        self,
        prompt: str,
        json_schema: dict[str, Any],
        *,
        max_output_tokens: int | None = None,
    ) -> Any:
        """Volanie API s JSON schema výstupom a bezpečným fallbackom.

        Preferuje Responses API s `response_format=json_schema`. Ak lokálna
        verzia SDK tento parameter nepodporuje, spadne do Chat Completions
        s rovnakým `response_format`. Ako posledný fallback použije obyčajné
        Chat Completions s inštrukciou odpovedať striktne JSON-om.
        """
        try:
            log.info("REQUEST → %s", prompt)
            content: str
            try:
                # Preferovaný spôsob (novšie SDK)
                resp = self.client.responses.create(  # type: ignore[call-overload]
                    model=self.model,
                    input=prompt,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "schema",
                            "schema": json_schema,
                            "strict": True,
                        },
                    },
                    stream=False,
                    max_output_tokens=max_output_tokens,
                )
                content = resp.output_text
            except TypeError as e:
                # Fallback: staršie SDK neakceptuje `response_format` pre Responses API.
                # Namiesto ďalších pokusov s `response_format` v Chat Completions,
                # preskoč rovno na režim bez schémy (inštrukcia v texte) — znižuje 400 chyby.
                log.warning(
                    (
                        "Responses API nepodporuje response_format – prechádzam "
                        "priamo na Chat Completions bez schema (dôvod=%s)"
                    ),
                    e,
                )
                try:
                    # Pokus 1: parameter max_completion_tokens
                    log.warning(
                        "chat.completions.create attempt "
                        "mode=no_schema token_param=max_completion_tokens"
                    )
                    chat = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {
                                "role": "user",
                                "content": (
                                    prompt
                                    + (
                                        "\nReply ONLY with strict JSON that matches the "
                                        "provided schema; no extra fields."
                                    )
                                ),
                            }
                        ],
                        max_completion_tokens=max_output_tokens,
                    )
                except Exception as e1:
                    # Pokus 2: parameter max_tokens
                    log.warning(
                        (
                            "chat.completions.create failed "
                            "(no_schema/max_completion_tokens): %s — retrying with max_tokens"
                        ),
                        e1,
                    )
                    chat = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {
                                "role": "user",
                                "content": (
                                    prompt
                                    + (
                                        "\nReply ONLY with strict JSON that matches the "
                                        "provided schema; no extra fields."
                                    )
                                ),
                            }
                        ],
                        max_tokens=max_output_tokens,
                    )
                content = (chat.choices[0].message.content or "")
            log.info("RESPONSE ← %s", content)
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:  # pravdepodobne orezanie JSON-u
                # ak výstup nevyzerá ako komplet JSON, považuj to za vyčerpanie limitu
                if not content.strip().endswith("}"):
                    msg = "Model output truncated (likely token limit)"
                    raise TokenBudgetExceededError(msg) from e
                raise
        except Exception as e:  # noqa: BLE001 - chceme vypisat vsetko
            log.exception("OpenAI call failed: %s", e)
            raise

    def _call_text(
        self,
        prompt: str,
        *,
        max_output_tokens: int | None = None,
    ) -> str:
        """Volanie API, ktoré vráti surový text.

        Komentár (SK): Preferujeme Responses API bez schema, s fallbackom na
        Chat Completions. Výstup logujeme pre audit/diagnostiku.
        """
        try:
            log.info("REQUEST → %s", prompt)
            try:
                resp = self.client.responses.create(
                    model=self.model,
                    input=prompt,
                    stream=False,
                    max_output_tokens=max_output_tokens,
                )
                content = resp.output_text
            except TypeError as e:
                log.warning(
                    "Responses API bez podpory parametrov — fallback chat.completions (reason=%s)",
                    e,
                )
                try:
                    chat = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        max_completion_tokens=max_output_tokens,
                    )
                except Exception:
                    chat = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_output_tokens,
                    )
                content = (chat.choices[0].message.content or "")
            log.info("RESPONSE ← %s", content)
            return content
        except Exception as e:  # noqa: BLE001
            log.exception("OpenAI call failed: %s", e)
            raise

    # ---------------- Rozhodca (batched) ----------------
    def judge_words(self, words: list[str]) -> JudgeBatchResponse:
        schema = {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "word": {"type": "string"},
                            "valid": {"type": "boolean"},
                            "reason": {"type": "string"},
                        },
                        "required": ["word", "valid", "reason"],
                        "additionalProperties": False,
                    },
                },
                "all_valid": {"type": "boolean"},
            },
            "required": ["results", "all_valid"],
            "additionalProperties": False,
        }
        sys_prompt = (
            "You are a strict Scrabble referee for English words. "
            "Reply with JSON only."
        )
        user_prompt = (
            "Validate these words for Scrabble play: "
            f"{words}. Return JSON exactly matching the schema."
        )
        raw = self._call_json(
            sys_prompt + "\n" + user_prompt,
            schema,
            max_output_tokens=self.judge_max_output_tokens,
        )

        if isinstance(raw, dict):
            normalized: list[JudgeResult] = []

            results = raw.get("results")
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        normalized.append(
                            {
                                "word": str(item.get("word", "")),
                                "valid": bool(item.get("valid", False)),
                                "reason": str(item.get("reason", "")),
                            }
                        )

            # Niektoré odpovede vracajú priamo jedno slovo (word/valid/...)
            if not normalized:
                single_word = raw.get("word")
                if isinstance(single_word, str):
                    reason = raw.get("reason")
                    if not isinstance(reason, str):
                        reason = str(raw.get("explanation", ""))
                    normalized.append(
                        {
                            "word": single_word,
                            "valid": bool(raw.get("valid", False)),
                            "reason": reason,
                        }
                    )

            # openai-python 1.x môže použiť kľúč "words": [...]
            if not normalized:
                alt_words = raw.get("words")
                if isinstance(alt_words, list):
                    for item in alt_words:
                        if isinstance(item, dict):
                            normalized.append(
                                {
                                    "word": str(item.get("word", "")),
                                    "valid": bool(item.get("valid", False)),
                                    "reason": str(item.get("reason", "")),
                                }
                            )

            if normalized:
                all_valid_raw = raw.get("all_valid")
                if isinstance(all_valid_raw, bool):
                    all_valid = bool(all_valid_raw)
                else:
                    all_valid = all(entry["valid"] for entry in normalized)
                if all_valid and not all(entry["valid"] for entry in normalized):
                    all_valid = False
                return cast(
                    JudgeBatchResponse,
                    {"results": normalized, "all_valid": all_valid},
                )
        elif isinstance(raw, list):
            normalized = []
            for item in raw:
                if isinstance(item, dict):
                    normalized.append(
                        {
                            "word": str(item.get("word", "")),
                            "valid": bool(item.get("valid", False)),
                            "reason": str(item.get("reason", "")),
                        }
                    )
            if normalized:
                all_valid = all(entry["valid"] for entry in normalized)
                return cast(
                    JudgeBatchResponse,
                    {"results": normalized, "all_valid": all_valid},
                )

        # Fallback: create minimal structure
        return cast(JudgeBatchResponse, {"results": [], "all_valid": False})

    # ---------------- AI hrac ----------------
    def propose_move(self, compact_state: str) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "placements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row": {"type": "integer"},
                            "col": {"type": "integer"},
                            "letter": {"type": "string"},
                        },
                        "required": ["row","col","letter"],
                        "additionalProperties": False,
                    },
                },
                "direction": {"type": "string", "enum": ["ACROSS","DOWN"]},
                "word": {"type": "string"},
                "exchange": {"type": "array", "items": {"type": "string"}},
                "pass": {"type": "boolean"},
                "blanks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row": {"type": "integer"},
                            "col": {"type": "integer"},
                            "as": {"type": "string"}
                        },
                        "required": ["row","col","as"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["placements","direction","word","exchange","pass","blanks"],
            "additionalProperties": False,
        }
        sys_prompt = (
            "You are an expert Scrabble player. Play to win. Reply with JSON only. "
            "Do NOT overwrite existing board letters; place only on EMPTY cells. "
            "Placements must form a single contiguous line with NO GAPS and "
            "must connect to existing letters after the first move. "
            "Use only letters from ai_rack; for '?' provide mapping in 'blanks' "
            "with chosen uppercase letter. "
            "If no legal move exists, set 'pass' true and leave placements empty. "
            "No explanations, no thoughts — JSON only."
        )
        user_prompt = (
            "Given this compact state, propose exactly one move with placements in a single line.\n"
            "If you use blanks from your rack, include them in 'blanks' with chosen letter.\n"
            f"State:\n{compact_state}"
        )
        raw = self._call_json(
            sys_prompt + "\n" + user_prompt,
            schema,
            max_output_tokens=self.ai_move_max_output_tokens,
        )
        if not isinstance(raw, dict):
            raise RuntimeError("AI move response is not a JSON object")
        return cast(dict[str, Any], raw)

class TokenBudgetExceededError(RuntimeError):
    """Vyvolané pri pravdepodobnom orezaní výstupu modelu kvôli limitu tokenov."""
