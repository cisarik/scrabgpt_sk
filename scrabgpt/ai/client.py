from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, TypedDict, cast

from dotenv import load_dotenv
from openai import OpenAI

from .fastdict import load_dictionary

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

        # Načítaj slovenský slovník pre rýchle vyhľadávanie
        self._slovak_dict: Callable[[str], bool] | None = None
        try:
            dict_path = Path(__file__).parent / "dicts" / "sk.sorted.txt"
            if dict_path.exists():
                self._slovak_dict = load_dictionary(dict_path)
                log.info("Slovak dictionary loaded from %s", dict_path)
        except Exception as e:
            log.warning("Failed to load Slovak dictionary: %s", e)

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
        """Validuje zoznam slov pre Scrabble.
        
        Pre slovenčinu: najprv kontroluje lokálny slovník, potom OpenAI ako fallback.
        Pre ostatné jazyky: používa len OpenAI.
        """
        # Pre slovenčinu: kontrola slovníka najprv
        if language.lower() == "slovak" and self._slovak_dict:
            dict_results: list[JudgeResult] = []
            openai_needed: list[str] = []
            
            for word in words:
                if self._slovak_dict(word):
                    dict_results.append({
                        "word": word,
                        "valid": True,
                        "reason": "Slovo nájdené v oficiálnom slovenskom slovníku.",
                    })
                else:
                    openai_needed.append(word)
            
            # Ak všetky slová našli sa v slovníku, vráť výsledky
            if not openai_needed:
                return cast(JudgeBatchResponse, {
                    "results": dict_results,
                    "all_valid": True,
                })
            
            # Inak spýtaj sa OpenAI len na nenájdené slová
            if dict_results:
                log.info(
                    "Dictionary check: %d/%d words found, asking OpenAI about %d words",
                    len(dict_results), len(words), len(openai_needed)
                )
                openai_response = self._judge_with_openai(openai_needed, language)
                combined_results = dict_results + openai_response["results"]
                all_valid = all(r["valid"] for r in combined_results)
                return cast(JudgeBatchResponse, {
                    "results": combined_results,
                    "all_valid": all_valid,
                })
            # Ak žiadne slová neboli v slovníku, pošli všetky do OpenAI
            words = openai_needed
        
        # Pre ostatné jazyky alebo ak slovník neexistuje: použiť len OpenAI
        return self._judge_with_openai(words, language)

    def _judge_with_openai(self, words: list[str], language: str) -> JudgeBatchResponse:
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

class TokenBudgetExceededError(RuntimeError):
    """Vyvolané pri pravdepodobnom orezaní výstupu modelu kvôli limitu tokenov."""
