from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, TypedDict, cast

from dotenv import load_dotenv
from openai import OpenAI, BadRequestError
from openai.types.chat import ChatCompletionMessageParam

from .fastdict import load_dictionary
from .juls_online import is_word_in_juls

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
        env_model = os.getenv("OPENAI_MODEL")
        if env_model:
            model = env_model

        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLMSTUDIO_BASE_URL")
        client_kwargs: dict[str, Any] = {}
        if base_url:
            client_kwargs["base_url"] = base_url.rstrip("/")
            log.info("OpenAI client base_url override: %s", client_kwargs["base_url"])

        self.client = OpenAI(api_key=api_key if api_key else None, **client_kwargs)
        self.model = model
        # LMStudio/localhost: vypneme Responses endpoint úplne (pády/500)
        if base_url:
            self._use_responses_endpoint = False
        else:
            self._use_responses_endpoint = True
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
            content: str = ""
            if self._use_responses_endpoint:
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
                    log.warning(
                        (
                            "Responses API nepodporuje response_format – prechádzam "
                            "priamo na Chat Completions bez schema (dôvod=%s)"
                        ),
                        e,
                    )
                except Exception as e:
                    log.warning("Responses API zlyhalo — fallback chat.completions (reason=%s)", e)
            if not content:
                try:
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
            content = ""
            # LMStudio/localhost: orez prompt ak je príliš dlhý (guard na overflow)
            local_prompt = prompt
            if not self._use_responses_endpoint and len(prompt) > 4000:
                local_prompt = prompt[-1800:]
                log.warning("Trimming prompt for local LLM (len=%d -> %d)", len(prompt), len(local_prompt))
            if self._use_responses_endpoint:
                try:
                    resp = self.client.responses.create(
                        model=self.model,
                        input=local_prompt,
                        stream=False,
                        max_output_tokens=max_output_tokens,
                    )
                    content = resp.output_text
                except Exception as e:
                    log.warning(
                        "Responses API zlyhalo — fallback chat.completions (reason=%s)",
                        e,
                    )
            if not content:
                try:
                    chat = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": local_prompt}],
                        max_completion_tokens=max_output_tokens,
                    )
                except BadRequestError as be:
                    if "context length" in str(be).lower():
                        log.warning("Context overflow detected, retrying with truncated prompt")
                        short_prompt = prompt[-1500:]
                        try:
                            chat = self.client.chat.completions.create(
                                model=self.model,
                                messages=[{"role": "user", "content": short_prompt}],
                                max_tokens=min(max_output_tokens or 512, 512),
                            )
                        except Exception as e2:
                            log.error("Retry after overflow failed: %s", e2)
                            raise
                    else:
                        raise
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

    def _call_text_with_context(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        max_output_tokens: int | None = None,
        stream_callback: "Callable[[str], None] | None" = None,
        reasoning_callback: "Callable[[str], None] | None" = None,
    ) -> tuple[str, dict[str, Any], dict[str, int]]:
        """Call with message history for reasoning models.
        
        Returns: (content, full_message) where full_message includes 'thinking' for reasoning models
        
        Komentár (SK): Táto metóda je optimalizovaná pre reasoning modely (deepseek-r1),
        ktoré používajú 'thinking' channel. Podporuje konverzáciu s históriou správ.
        """
        try:
            log.info("REQUEST (context) → %d messages", len(messages))
            if log.isEnabledFor(logging.DEBUG):
                for idx, msg in enumerate(messages):
                    role = msg.get("role", "?")
                    content = str(msg.get("content", ""))[:200]
                    log.debug("  [%d] %s: %s...", idx, role, content)
            
            usage_info: dict[str, int] = {}
            full_message: dict[str, Any] = {"role": "assistant", "content": ""}
            
            if stream_callback:
                # Streaming path
                try:
                    stream = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_completion_tokens=max_output_tokens,
                        stream=True,
                    )
                except BadRequestError as be:
                    if "context length" in str(be).lower():
                        log.warning("Stream context overflow, retrying with trimmed history (system + last user)")
                        trimmed = messages[:1] + messages[-1:]
                        stream = self.client.chat.completions.create(
                            model=self.model,
                            messages=trimmed,
                            max_tokens=min(max_output_tokens or 512, 512),
                            stream=True,
                        )
                    else:
                        raise
                except Exception:
                    stream = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_tokens=max_output_tokens,
                        stream=True,
                    )
                
                collected: list[str] = []
                reasoning_mode = False
                for chunk in stream:
                    delta = ""
                    reasoning_delta = ""
                    if chunk.choices and chunk.choices[0].delta:
                        delta = chunk.choices[0].delta.content or ""
                        # LMStudio/OpenAI reasoning
                        reasoning_delta = getattr(chunk.choices[0].delta, "reasoning_content", None) or ""
                        if hasattr(chunk.choices[0].delta, "thinking"):
                            reasoning_delta = reasoning_delta or getattr(chunk.choices[0].delta, "thinking", "") or ""
                    if reasoning_delta and reasoning_callback:
                        # ak reasoning delta prichádza mimo tagov, odošli priamo
                        reasoning_callback(reasoning_delta)
                    
                    if delta:
                        # Parsuj <think> bloky v delta, aby reasoning šiel do separátnej bubliny
                        text_remaining = delta
                        while text_remaining:
                            if reasoning_mode:
                                end_idx = text_remaining.find("</think>")
                                if end_idx != -1:
                                    chunk_reason = text_remaining[:end_idx]
                                    if chunk_reason and reasoning_callback:
                                        reasoning_callback(chunk_reason)
                                    reasoning_mode = False
                                    text_remaining = text_remaining[end_idx + len("</think>") :]
                                else:
                                    if reasoning_callback:
                                        reasoning_callback(text_remaining)
                                    text_remaining = ""
                            else:
                                start_idx = text_remaining.find("<think>")
                                if start_idx != -1:
                                    before = text_remaining[:start_idx]
                                    if before:
                                        collected.append(before)
                                        stream_callback(before)
                                    reasoning_mode = True
                                    text_remaining = text_remaining[start_idx + len("<think>") :]
                                else:
                                    collected.append(text_remaining)
                                    stream_callback(text_remaining)
                                    text_remaining = ""
                content = "".join(collected)
                full_message["content"] = content
                log.info("RESPONSE (stream) ← content=%d chars", len(content))
            else:
                try:
                    # Try with max_completion_tokens first (preferred for newer models)
                    chat = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_completion_tokens=max_output_tokens,
                    )
                except BadRequestError as be:
                    if "context length" in str(be).lower():
                        log.warning("Context overflow (non-stream), retrying with trimmed history")
                        trimmed = messages[:1] + messages[-1:]
                        chat = self.client.chat.completions.create(
                            model=self.model,
                            messages=trimmed,
                            max_tokens=min(max_output_tokens or 512, 512),
                        )
                    else:
                        raise
                except Exception as e:
                    log.warning("max_completion_tokens failed, trying max_tokens: %s", e)
                    chat = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_tokens=max_output_tokens,
                    )
                
                message = chat.choices[0].message
                content_raw = message.content or ""
                reasoning_block = ""
                # Extract <think>...</think> if present
                if "<think>" in content_raw and "</think>" in content_raw:
                    start_idx = content_raw.find("<think>") + len("<think>")
                    end_idx = content_raw.find("</think>")
                    reasoning_block = content_raw[start_idx:end_idx].strip()
                    content = content_raw[end_idx + len("</think>") :].lstrip()
                else:
                    content = content_raw
                full_message["content"] = content
                
                # Check for reasoning/thinking content (deepseek-r1 specific)
                if hasattr(message, 'thinking') and message.thinking:
                    full_message["thinking"] = message.thinking
                    log.info("RESPONSE (context) ← content=%d chars, thinking=%d chars", 
                             len(content), len(message.thinking))
                elif hasattr(message, 'reasoning') and message.reasoning:
                    full_message["reasoning"] = message.reasoning
                    log.info("RESPONSE (context) ← content=%d chars, reasoning=%d chars", 
                             len(content), len(message.reasoning))
                elif reasoning_block:
                    full_message["reasoning"] = reasoning_block
                    if reasoning_callback:
                        reasoning_callback(reasoning_block)
                    log.info("RESPONSE (context) ← content=%d chars, reasoning(block)=%d chars",
                             len(content), len(reasoning_block))
                else:
                    log.info("RESPONSE (context) ← content=%d chars", len(content))
                
                if log.isEnabledFor(logging.DEBUG):
                    log.debug("Response content: %s", content[:300])
                    if "thinking" in full_message:
                        log.debug("Thinking: %s", full_message["thinking"][:200])
                    if "reasoning" in full_message:
                        log.debug("Reasoning: %s", full_message["reasoning"][:200])
                
                try:
                    usage = getattr(chat, "usage", None)
                    if usage:
                        prompt_tokens_raw: Any = 0
                        if hasattr(usage, "prompt_tokens"):
                            prompt_tokens_raw = getattr(usage, "prompt_tokens", 0)
                        elif isinstance(usage, dict):
                            prompt_tokens_raw = usage.get("prompt_tokens", 0)
                        prompt_tokens = int(prompt_tokens_raw or 0)
                        context_len = 0
                        if hasattr(chat, "model") and getattr(chat, "model", None):
                            from .lmstudio_utils import get_context_length
                            context_len = get_context_length(getattr(chat, "model"))
                        usage_info = {"prompt_tokens": prompt_tokens, "context_length": context_len}
                except Exception as exc:  # noqa: BLE001
                    log.debug("Usage extraction failed: %s", exc)
            
            return content, full_message, usage_info
        except Exception as e:  # noqa: BLE001
            log.exception("Chat completion with context failed: %s", e)
            raise

    # ---------------- Rozhodca (batched) ----------------
    def judge_words(self, words: list[str], *, language: str) -> JudgeBatchResponse:
        """Validuje zoznam slov pre Scrabble.
        
        Pre slovenčinu: 3-stupňová validácia:
        1. Lokálny slovník (najrýchlejšie)
        2. Online JÚĽŠ slovník (stredne rýchle)
        3. OpenAI (najdrahšie, len ako posledná možnosť)
        
        Pre ostatné jazyky: používa len OpenAI.
        """
        # Pre slovenčinu: kontrola slovníka najprv
        if language.lower() == "slovak" and self._slovak_dict:
            dict_results: list[JudgeResult] = []
            juls_needed: list[str] = []
            
            # Úroveň 1: Lokálny slovník
            for word in words:
                if self._slovak_dict(word):
                    dict_results.append({
                        "word": word,
                        "valid": True,
                        "reason": "Slovo nájdené v oficiálnom slovenskom slovníku.",
                    })
                else:
                    juls_needed.append(word)
            
            # Ak všetky slová našli sa v lokálnom slovníku, vráť výsledky
            if not juls_needed:
                return cast(JudgeBatchResponse, {
                    "results": dict_results,
                    "all_valid": True,
                })
            
            # Úroveň 2: Online JÚĽŠ slovník pre slová nenájdené lokálne
            juls_results: list[JudgeResult] = []
            openai_needed: list[str] = []
            
            log.info(
                "Local dictionary: %d/%d words found, checking JULS for %d words",
                len(dict_results), len(words), len(juls_needed)
            )
            
            for word in juls_needed:
                try:
                    if is_word_in_juls(word):
                        result: JudgeResult = {
                            "word": word,
                            "valid": True,
                            "reason": "Slovo nájdené v online slovníku JÚĽŠ.",
                        }
                        juls_results.append(result)
                    else:
                        openai_needed.append(word)
                except Exception as e:
                    # Pri chybe JÚĽŠ (network timeout, atď), pridaj do OpenAI fronty
                    log.warning("JULS lookup failed for '%s': %s, falling back to OpenAI", word, e)
                    openai_needed.append(word)
            
            combined_results = dict_results + juls_results
            
            # Ak všetky slová našli sa v slovníkoch (lokálny + JÚĽŠ), vráť výsledky
            if not openai_needed:
                log.info(
                    "JULS online: %d/%d remaining words found",
                    len(juls_results), len(juls_needed)
                )
                return cast(JudgeBatchResponse, {
                    "results": combined_results,
                    "all_valid": True,
                })
            
            # Úroveň 3: OpenAI pre slová nenájdené ani v JÚĽŠ
            log.info(
                "JULS online: %d/%d found, asking OpenAI about final %d words",
                len(juls_results), len(juls_needed), len(openai_needed)
            )
            try:
                openai_response = self._judge_with_openai(openai_needed, language)
            except Exception as e:  # noqa: BLE001
                log.exception("OpenAI judge fallback failed: %s", e)
                # Mark unresolved words as invalid but keep previous findings
                error_results: list[JudgeResult] = [
                    {"word": w, "valid": False, "reason": f"OpenAI judge failed: {e}"}
                    for w in openai_needed
                ]
                combined_results = combined_results + error_results
                all_valid = all(r["valid"] for r in combined_results)
                return cast(JudgeBatchResponse, {
                    "results": combined_results,
                    "all_valid": all_valid,
                })
            combined_results = combined_results + openai_response["results"]
            all_valid = all(r["valid"] for r in combined_results)
            return cast(JudgeBatchResponse, {
                "results": combined_results,
                "all_valid": all_valid,
            })
        
        # Pre ostatné jazyky alebo ak slovník neexistuje: použiť len OpenAI
        return self._judge_with_openai(words, language)

    def _judge_with_openai(self, words: list[str], language: str) -> JudgeBatchResponse:
        if not words:
            return cast(JudgeBatchResponse, {"results": [], "all_valid": True})
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

            # Niektoré odpovede môžu mať tvar {"SLOVO": {"valid": true, ...}}
            if not normalized:
                raw_word_map: list[dict[str, Any]] = []
                for key, value in raw.items():
                    if not isinstance(key, str) or not isinstance(value, dict):
                        continue
                    word_field = value.get("word") if isinstance(value.get("word"), str) else None
                    word = (word_field or key).strip()
                    if not word:
                        continue
                    entry = dict(value)
                    entry["word"] = word
                    valid_flag = _resolve_valid_flag(value)
                    entry["valid"] = bool(valid_flag) if valid_flag is not None else bool(value.get("valid", False))
                    entry["reason"] = _normalize_reason(entry)
                    raw_word_map.append(entry)
                if raw_word_map:
                    seen: set[str] = set()
                    for entry in raw_word_map:
                        word = entry.get("word")
                        if not isinstance(word, str):
                            continue
                        key_cf = word.casefold()
                        if key_cf in seen:
                            continue
                        seen.add(key_cf)
                        normalized.append(cast(JudgeResult, entry))

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
