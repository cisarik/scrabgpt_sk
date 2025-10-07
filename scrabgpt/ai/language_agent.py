"""Language Agent - Async MCP agent for fetching supported languages.

This is a learning example of how to use MCP agents in ScrabGPT.
It shows the pattern for:
1. Async agent execution
2. Progress/status callbacks
3. Error handling
4. Result caching
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .client import OpenAIClient
from .variants import LanguageInfo, _VARIANTS_DIR, _LANG_CACHE_PATH, _ensure_variants_dir

log = logging.getLogger("scrabgpt.ai.language_agent")


@dataclass
class AgentProgress:
    """Progress update from agent."""
    status: str
    thinking: str | None = None
    progress_percent: int | None = None
    prompt_text: str | None = None  # Actual prompt to show in green


class LanguageAgent:
    """Agent for fetching supported languages using async MCP pattern.
    
    This agent:
    1. Calls OpenAI to get list of supported languages
    2. Parses and validates the response
    3. Caches results for future use
    4. Reports progress via callbacks
    
    Example usage:
        agent = LanguageAgent(api_key="sk-...")
        
        def on_progress(update: AgentProgress):
            print(f"Status: {update.status}")
            if update.thinking:
                print(f"Thinking: {update.thinking}")
        
        languages = await agent.fetch_languages(
            on_progress=on_progress,
            use_cache=True
        )
    """
    
    def __init__(self, api_key: str | None = None) -> None:
        """Initialize language agent.
        
        Args:
            api_key: OpenAI API key (defaults to env var)
        """
        self.api_key = api_key
        self._client: Optional[OpenAIClient] = None
    
    def _get_client(self) -> OpenAIClient:
        """Get or create OpenAI client."""
        if self._client is None:
            if self.api_key:
                import os
                old_key = os.environ.get("OPENAI_API_KEY")
                os.environ["OPENAI_API_KEY"] = self.api_key
                try:
                    self._client = OpenAIClient()
                finally:
                    if old_key:
                        os.environ["OPENAI_API_KEY"] = old_key
                    else:
                        os.environ.pop("OPENAI_API_KEY", None)
            else:
                self._client = OpenAIClient()
        return self._client
    
    async def fetch_languages(
        self,
        *,
        on_progress: Callable[[AgentProgress], None] | None = None,
        use_cache: bool = True,
        min_languages: int = 40,
    ) -> list[LanguageInfo]:
        """Fetch supported languages asynchronously.
        
        Args:
            on_progress: Callback for progress updates
            use_cache: Whether to try loading from cache first
            min_languages: Minimum number of languages to request
        
        Returns:
            List of LanguageInfo objects
        
        Raises:
            ValueError: If no languages returned or API error
        """
        def report(
            status: str,
            thinking: str | None = None,
            progress: int | None = None,
            prompt_text: str | None = None,
        ) -> None:
            """Helper to report progress."""
            if on_progress:
                on_progress(AgentProgress(
                    status=status,
                    thinking=thinking,
                    progress_percent=progress,
                    prompt_text=prompt_text,
                ))
        
        try:
            # Step 1: Try cache if enabled
            if use_cache:
                report("Kontrolujem cache...", thinking="Hľadám už stiahnuté jazyky v lokálnej cache")
                cached = await asyncio.to_thread(self._load_from_cache)
                if cached:
                    report(
                        f"Načítané z cache ({len(cached)} jazykov)",
                        thinking="Našiel som uložené jazyky, nemusím volať API"
                    )
                    return cached
                report("Cache prázdna", thinking="Cache neobsahuje jazyky, budem volať OpenAI API")
            
            # Step 2: Initialize client
            report("Pripájam sa k OpenAI...", thinking="Inicializujem OpenAI klienta", progress=20)
            client = await asyncio.to_thread(self._get_client)
            
            # Step 3: Prepare prompt
            prompt = await asyncio.to_thread(
                self._build_prompt,
                min_languages=min_languages,
            )
            report(
                "Pripravujem požiadavku...",
                thinking="Zostavujem prompt pre GPT model",
                progress=40,
                prompt_text=prompt,  # Show actual prompt in green
            )
            
            # Step 4: Call OpenAI API
            report(
                "Volám OpenAI API...",
                thinking=f"Posielam prompt GPT modelu, požadujem aspoň {min_languages} jazykov",
                progress=60,
            )
            
            response_data = await asyncio.to_thread(
                self._call_openai,
                client=client,
                prompt=prompt,
            )
            
            # Step 5: Parse and validate response
            report(
                "Spracovávam odpoveď...",
                thinking="Parsovanie JSON odpovede a validácia dát",
                progress=80,
            )
            
            languages = await asyncio.to_thread(
                self._parse_response,
                response_data,
            )
            
            if not languages:
                raise ValueError("OpenAI nevrátil žiadne jazyky")
            
            # Step 6: Save to cache
            report(
                "Ukladám do cache...",
                thinking=f"Zapisujem {len(languages)} jazykov do lokálnej cache",
                progress=90,
            )
            
            await asyncio.to_thread(
                self._save_to_cache,
                languages,
            )
            
            # Done!
            report(
                f"Hotovo! Načítaných {len(languages)} jazykov",
                thinking="Všetky jazyky úspešne načítané a uložené",
                progress=100,
            )
            
            return languages
        
        except Exception as e:
            log.exception("Language agent failed: %s", e)
            report(
                f"Chyba: {e}",
                thinking=f"Agent zlyhal s chybou: {type(e).__name__}",
            )
            raise
    
    def _load_from_cache(self) -> list[LanguageInfo] | None:
        """Load languages from cache file."""
        _ensure_variants_dir()
        if not _LANG_CACHE_PATH.exists():
            return None
        
        try:
            payload = json.loads(_LANG_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Failed to load language cache: %s", exc)
            return None
        
        languages_raw = payload.get("languages", [])
        languages: list[LanguageInfo] = []
        
        for item in languages_raw:
            if not isinstance(item, dict):
                continue
            
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            
            code_raw = item.get("code")
            code = str(code_raw).strip() if isinstance(code_raw, str) else None
            
            aliases_raw = item.get("aliases", [])
            aliases = tuple(str(a).strip() for a in aliases_raw if str(a).strip()) if isinstance(aliases_raw, list) else ()
            
            script_raw = item.get("script")
            script = str(script_raw).strip() if isinstance(script_raw, str) else None
            
            languages.append(LanguageInfo(
                name=name,
                code=code,
                aliases=aliases,
                script=script,
            ))
        
        return languages if languages else None
    
    def _build_prompt(self, min_languages: int) -> str:
        """Build prompt for OpenAI."""
        return (
            f"Zostav JSON so zoznamom prirodzených jazykov, v ktorých dokážeš spoľahlivo "
            f"komunikovať. Vráť aspoň {min_languages} jazykov naprieč svetadielmi. Pre každý jazyk "
            "uved' kľúče 'name' (anglický názov), 'code' (ISO 639-1 alebo 639-3, ak "
            "existuje), 'aliases' (alternatívne názvy alebo názvy v slovenčine, použi prázdne "
            "pole ak žiadne nemáš) a 'script' (napr. Latin, Cyrillic). Odpovedz výhradne JSON "
            "objektom so štruktúrou languages=[...]."
        )
    
    def _call_openai(self, client: OpenAIClient, prompt: str) -> dict:
        """Call OpenAI API synchronously (to be wrapped in asyncio.to_thread)."""
        schema = {
            "type": "object",
            "properties": {
                "languages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "code": {"type": "string"},
                            "aliases": {"type": "array", "items": {"type": "string"}},
                            "script": {"type": "string"},
                        },
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["languages"],
            "additionalProperties": False,
        }
        
        return client._call_json(prompt, schema)
    
    def _parse_response(self, data: dict) -> list[LanguageInfo]:
        """Parse OpenAI response into LanguageInfo objects."""
        languages: list[LanguageInfo] = []
        
        if not isinstance(data, dict):
            return languages
        
        for item in data.get("languages", []):
            if not isinstance(item, dict):
                continue
            
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            
            code_raw = item.get("code")
            code = str(code_raw).strip() if isinstance(code_raw, str) and code_raw else None
            
            aliases_raw = item.get("aliases", [])
            aliases = tuple(str(a).strip() for a in aliases_raw if str(a).strip()) if isinstance(aliases_raw, list) else ()
            
            script_raw = item.get("script")
            script = str(script_raw).strip() if isinstance(script_raw, str) and script_raw else None
            
            languages.append(LanguageInfo(
                name=name,
                code=code,
                aliases=aliases,
                script=script,
            ))
        
        # Deduplicate by name
        dedup: dict[str, LanguageInfo] = {}
        for lang in languages:
            key = lang.name.casefold()
            if key not in dedup:
                dedup[key] = lang
        
        return sorted(dedup.values(), key=lambda item: item.name.lower())
    
    def _save_to_cache(self, languages: list[LanguageInfo]) -> None:
        """Save languages to cache file."""
        _ensure_variants_dir()
        
        payload = {
            "languages": [
                {
                    "name": lang.name,
                    "code": lang.code,
                    "aliases": list(lang.aliases),
                    "script": lang.script,
                }
                for lang in languages
            ]
        }
        
        _LANG_CACHE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        
        log.info("Saved %d languages to cache: %s", len(languages), _LANG_CACHE_PATH)
