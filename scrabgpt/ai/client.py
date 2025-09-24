from __future__ import annotations

import json
import logging
import os
from typing import Any, Sequence, TypedDict, cast

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

class DisputeJudgeResult(TypedDict):
    word: str
    valid: bool
    reason: str
    attempts_left: int

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
    def judge_words(self, words: list[str], *, language: str) -> JudgeBatchResponse:
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
            f"You are a strict Scrabble referee for {language} words. "
            "Reply with JSON only. "
            "Use the official Scrabble lexicon as primary evidence. "
            "Also consider attested usage in real sentences and corpora when judging legality. "
            "If a word is naturally used as an independent {language} word, treat it as playable even "
            "when it lacks an entry in the lexicon. "
        )
        if language.lower() == "slovak":
            sys_prompt += (
                "Diacritics is very important so distinguishing between 'Ú' and 'U' for example and every letter with diacritic"
                "For each word, confirm it can stand on its own in a natural Slovak sentence. "
                "Treat regular inflected forms of recognised lemmas "
                "(like plurals or case variants) as valid even without lexicon coverage. "
                "Before rejecting a word, actively look for its use in idioms, sayings, "
                "imperatives, or other fixed Slovak expressions. If you can produce a "
                "credible natural sentence that uses the exact form as an independent word, "
                "declare it valid and cite that sentence in the reason. Always return the "
                "'reason' text strictly in Slovak, even when citing evidence. Only label a word "
                "invalid when you are confident no such natural usage exists."
            )
        user_prompt = (
            f"Validate these words for {language} Scrabble play: {words}. "
            "Return JSON exactly matching the schema."
        )
        raw = self._call_json(
            sys_prompt + "\n" + user_prompt,
            schema,
            max_output_tokens=self.judge_max_output_tokens,
        )

        if isinstance(raw, dict):
            normalized: list[JudgeResult] = []
            reserved_keys = {
                "results",
                "words",
                "all_valid",
                "word",
                "valid",
                "reason",
                "explanation",
                "is_valid",
                "is_playable",
                "playable",
                "legal",
                "is_legal",
                "allowed",
            }

            def _resolve_valid_flag(data: dict[str, Any]) -> bool | None:
                """Extract a boolean validity flag from diverse model fields."""
                for key in ("valid", "is_valid", "is_playable", "playable", "legal", "is_legal", "allowed"):
                    value = data.get(key)
                    if isinstance(value, bool):
                        return bool(value)
                return None

            def _normalize_reason(data: dict[str, Any]) -> str:
                reason = data.get("reason")
                if isinstance(reason, str) and reason.strip():
                    return reason
                explanation = data.get("explanation")
                if isinstance(explanation, str) and explanation.strip():
                    return explanation
                evidence = data.get("evidence")
                if isinstance(evidence, list):
                    parts: list[str] = []
                    for item in evidence:
                        if isinstance(item, str):
                            parts.append(item)
                    if parts:
                        return " | ".join(parts)
                return ""

            results = raw.get("results")
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        valid_flag = _resolve_valid_flag(item)
                        normalized.append(
                            {
                                "word": str(item.get("word", "")),
                                "valid": bool(valid_flag) if valid_flag is not None else bool(item.get("valid", False)),
                                "reason": _normalize_reason(item),
                            }
                        )

            # Niektoré odpovede vracajú priamo jedno slovo (word/valid/...)
            if not normalized:
                single_word = raw.get("word")
                if isinstance(single_word, str):
                    valid_flag = _resolve_valid_flag(raw)
                    normalized.append(
                        {
                            "word": single_word,
                            "valid": bool(valid_flag) if valid_flag is not None else bool(raw.get("valid", False)),
                            "reason": _normalize_reason(raw),
                        }
                    )

            # openai-python 1.x môže použiť kľúč "words": [...]
            if not normalized:
                alt_words = raw.get("words")
                if isinstance(alt_words, list):
                    for item in alt_words:
                        if isinstance(item, dict):
                            valid_flag = _resolve_valid_flag(item)
                            normalized.append(
                                {
                                    "word": str(item.get("word", "")),
                                    "valid": bool(valid_flag) if valid_flag is not None else bool(item.get("valid", False)),
                                    "reason": _normalize_reason(item),
                                }
                            )

            # Niektoré odpovede môžu mať tvar {"SLOVO": true, ...}
            if not normalized:
                bool_map = {
                    k: v
                    for k, v in raw.items()
                    if isinstance(k, str)
                    and k not in reserved_keys
                    and isinstance(v, bool)
                }
                if bool_map:
                    used_keys: set[str] = set()

                    def _fallback_reason(valid: bool) -> str:
                        if valid:
                            return "Model confirmed validity without explanation."
                        return "Model rejected word without explanation."

                    for expected in words:
                        if not isinstance(expected, str):
                            continue
                        value = None
                        if expected in bool_map:
                            value = bool_map[expected]
                            used_keys.add(expected)
                        else:
                            expected_cf = expected.casefold()
                            for key, val in bool_map.items():
                                if key in used_keys:
                                    continue
                                if key.casefold() == expected_cf:
                                    value = val
                                    used_keys.add(key)
                                    break
                        if value is not None:
                            normalized.append(
                                {
                                    "word": expected,
                                    "valid": bool(value),
                                    "reason": _fallback_reason(bool(value)),
                                }
                            )

                    for key, value in bool_map.items():
                        if key in used_keys:
                            continue
                        normalized.append(
                            {
                                "word": key,
                                "valid": bool(value),
                                "reason": _fallback_reason(bool(value)),
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

    def dispute_word(
        self,
        *,
        word: str,
        language: str,
        history: Sequence[tuple[str, str]],
        attempts_left: int,
    ) -> DisputeJudgeResult:
        """Prehodnotí jedno slovo na základe argumentácie hráča."""

        schema = {
            "type": "object",
            "properties": {
                "word": {"type": "string"},
                "valid": {"type": "boolean"},
                "reason": {"type": "string"},
                "attempts_left": {"type": "integer", "minimum": 0},
            },
            "required": ["word", "valid", "reason", "attempts_left"],
            "additionalProperties": False,
        }

        convo_lines: list[str] = []
        for role, message in history:
            label = "Rozhodca" if role == "referee" else "Hráč"
            convo_lines.append(f"{label}: {message}")
        conversation = "\n".join(convo_lines) if convo_lines else "(Žiadna konverzácia)"

        sys_prompt = (
            "Si rozhodca slovenského Scrabble, ktorý pôvodne slovo zamietol a teraz "
            "vyhodnocuje nové argumenty hráča. Rozhoduj striktne podľa slovenských "
            "Scrabble pravidiel a vráť odpoveď presne vo forme JSON zodpovedajúcej "
            "poskytnutej schéme. "
            "Pole 'valid' nastav na true len ak aktuálne uznávaš slovo ako platné. "
            "Do 'reason' vlož stručné odôvodnenie v slovenčine (1–3 vety). "
            "Pole 'attempts_left' nastav na počet pokusov, ktoré hráč ešte môže využiť "
            "po tomto vyhodnotení (nepôsob, keď už sú 0)."
        )

        user_prompt = (
            f"Posudzované slovo: {word}\n"
            f"Jazyk: {language}\n"
            f"Zostávajúce pokusy hráča po tomto vyhodnotení: {attempts_left}\n"
            "Konverzácia doteraz (chronologicky):\n"
            f"{conversation}\n"
            "Vráť výstup ako JSON presne podľa schémy (žiadny text mimo JSON)."
        )

        raw = self._call_json(
            sys_prompt + "\n" + user_prompt,
            schema,
            max_output_tokens=self.judge_max_output_tokens,
        )

        if not isinstance(raw, dict):
            raise ValueError("Neplatná odpoveď rozhodcu pri spornej argumentácii")

        word_value = str(raw.get("word", word)).strip() or word
        valid_value = bool(raw.get("valid", False))
        reason_value = str(raw.get("reason", "")).strip()
        attempts_reported = raw.get("attempts_left")
        if not isinstance(attempts_reported, int) or attempts_reported < 0:
            attempts_reported = max(0, attempts_left)

        if not reason_value:
            if valid_value:
                reason_value = "Rozhodca uznal platnosť bez dodatočného vysvetlenia."
            else:
                reason_value = "Rozhodca odmietol bez dodatočného vysvetlenia."

        return {
            "word": word_value,
            "valid": valid_value,
            "reason": reason_value,
            "attempts_left": attempts_reported,
        }

    # ---------------- AI hrac ----------------
    def propose_move(
        self,
        compact_state: str,
        *,
        language: str,
        tile_summary: str | None = None,
    ) -> dict[str, Any]:
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
            f"You are an expert Scrabble player for the {language} language variant. "
            "Play to win. Reply with JSON only. Do NOT overwrite existing board letters; "
            "place only on empty cells. Placements must form a single contiguous line with no gaps "
            "and must connect to existing letters after the first move. Use only letters from ai_rack; "
            "for '?' provide mapping in 'blanks' with chosen uppercase letter. If no legal move exists, "
            "set 'pass' true and leave placements empty."
        )
        if tile_summary:
            sys_prompt += f" Tile distribution summary: {tile_summary}."
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
