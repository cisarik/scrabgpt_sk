from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Sequence

from ..core.assets import get_assets_path
from ..core.variant_store import VariantDefinition, save_variant, slugify, variant_exists
from .client import OpenAIClient

log = logging.getLogger("scrabgpt.ai.variants")

_VARIANTS_DIR = get_assets_path() / "variants"
_LANG_CACHE_PATH = _VARIANTS_DIR / "openai_languages.json"


@dataclass(frozen=True)
class LanguageInfo:
    """Základná informácia o jazyku, ktorý môže byť podporovaný."""

    name: str
    code: str | None = None
    aliases: tuple[str, ...] = ()
    script: str | None = None

    def display_label(self) -> str:
        if self.code:
            return f"{self.name} ({self.code})"
        return self.name

    def matches(self, query: str) -> bool:
        q = query.strip().casefold()
        if not q:
            return False
        if self.name.casefold() == q:
            return True
        if self.code and self.code.casefold() == q:
            return True
        return any(alias.casefold() == q for alias in self.aliases)


def _ensure_variants_dir() -> None:
    _VARIANTS_DIR.mkdir(parents=True, exist_ok=True)


def load_cached_languages() -> list[LanguageInfo]:
    _ensure_variants_dir()
    if not _LANG_CACHE_PATH.exists():
        return []
    try:
        payload = json.loads(_LANG_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("language_cache_parse_failed path=%s error=%s", _LANG_CACHE_PATH, exc)
        return []
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
        aliases: tuple[str, ...]
        if isinstance(aliases_raw, list):
            aliases = tuple(str(alias).strip() for alias in aliases_raw if str(alias).strip())
        else:
            aliases = ()
        script_raw = item.get("script")
        script = str(script_raw).strip() if isinstance(script_raw, str) and script_raw else None
        languages.append(LanguageInfo(name=name, code=code or None, aliases=aliases, script=script))
    return languages


def save_language_cache(languages: Sequence[LanguageInfo]) -> Path:
    _ensure_variants_dir()
    payload = {
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds"),
        "languages": [
            {
                "name": lang.name,
                "code": lang.code,
                "aliases": list(lang.aliases),
                "script": lang.script,
            }
            for lang in languages
        ],
    }
    _LANG_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return _LANG_CACHE_PATH


_FALLBACK_LANGUAGES: tuple[LanguageInfo, ...] = (
    LanguageInfo("English", "en", aliases=("angličtina", "english")),
    LanguageInfo("Slovak", "sk", aliases=("slovenčina", "slovak")),
    LanguageInfo("Czech", "cs", aliases=("čeština", "czech")),
    LanguageInfo("Polish", "pl", aliases=("polština", "polish")),
    LanguageInfo("German", "de", aliases=("nemčina", "german")),
    LanguageInfo("French", "fr", aliases=("francúzština", "french")),
    LanguageInfo("Spanish", "es", aliases=("španielčina", "spanish")),
    LanguageInfo("Portuguese", "pt", aliases=("portugalčina", "portuguese")),
    LanguageInfo("Italian", "it", aliases=("taliančina", "italian")),
    LanguageInfo("Hungarian", "hu", aliases=("maďarčina", "hungarian")),
    LanguageInfo("Dutch", "nl", aliases=("holandčina", "dutch")),
    LanguageInfo("Swedish", "sv", aliases=("švédčina", "swedish")),
    LanguageInfo("Norwegian", "nb", aliases=("nórčina", "norwegian")),
    LanguageInfo("Finnish", "fi", aliases=("fínčina", "finnish")),
    LanguageInfo("Danish", "da", aliases=("dánčina", "danish")),
    LanguageInfo("Icelandic", "is", aliases=("islandčina", "icelandic")),
    LanguageInfo("Greek", "el", aliases=("gréčtina", "greek")),
    LanguageInfo("Turkish", "tr", aliases=("turečtina", "turkish")),
    LanguageInfo("Romanian", "ro", aliases=("rumunčina", "romanian")),
    LanguageInfo("Bulgarian", "bg", aliases=("bulharčina", "bulgarian")),
    LanguageInfo("Serbian", "sr", aliases=("srbčina", "serbian")),
    LanguageInfo("Croatian", "hr", aliases=("chorvátčina", "croatian")),
    LanguageInfo("Bosnian", "bs", aliases=("bosniančina", "bosnian")),
    LanguageInfo("Slovenian", "sl", aliases=("slovinčina", "slovenian")),
    LanguageInfo("Ukrainian", "uk", aliases=("ukrajinčina", "ukrainian")),
    LanguageInfo("Russian", "ru", aliases=("ruština", "russian")),
    LanguageInfo("Belarusian", "be", aliases=("bieloruština", "belarusian")),
    LanguageInfo("Latvian", "lv", aliases=("lotyština", "latvian")),
    LanguageInfo("Lithuanian", "lt", aliases=("litovčina", "lithuanian")),
    LanguageInfo("Estonian", "et", aliases=("estónčina", "estonian")),
    LanguageInfo("Irish", "ga", aliases=("írčina", "irish")),
    LanguageInfo("Welsh", "cy", aliases=("waleština", "welsh")),
    LanguageInfo("Catalan", "ca", aliases=("katalánčina", "catalan")),
    LanguageInfo("Basque", "eu", aliases=("baskičtina", "basque")),
    LanguageInfo("Galician", "gl", aliases=("galícijčina", "galician")),
    LanguageInfo("Arabic", "ar", aliases=("arabčina", "arabic")),
    LanguageInfo("Hebrew", "he", aliases=("hebrejčina", "hebrew")),
    LanguageInfo("Persian", "fa", aliases=("perzština", "persian", "farsi")),
    LanguageInfo("Hindi", "hi", aliases=("hindčina", "hindi")),
    LanguageInfo("Bengali", "bn", aliases=("bengálčina", "bengali")),
    LanguageInfo("Punjabi", "pa", aliases=("pandžábčina", "punjabi")),
    LanguageInfo("Urdu", "ur", aliases=("urdčina", "urdu")),
    LanguageInfo("Indonesian", "id", aliases=("indonézština", "indonesian")),
    LanguageInfo("Malay", "ms", aliases=("malajčina", "malay")),
    LanguageInfo("Thai", "th", aliases=("thajčina", "thai")),
    LanguageInfo("Vietnamese", "vi", aliases=("vietnamčina", "vietnamese")),
    LanguageInfo("Chinese", "zh", aliases=("čínština", "chinese")),
    LanguageInfo("Japanese", "ja", aliases=("japončina", "japanese")),
    LanguageInfo("Korean", "ko", aliases=("kórejčina", "korean")),
)


def get_languages_for_ui() -> list[LanguageInfo]:
    cached = load_cached_languages()
    if cached:
        return cached
    return list(_FALLBACK_LANGUAGES)


_LANGUAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "languages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "code": {"type": ["string", "null"]},
                    "aliases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                    "script": {"type": ["string", "null"]},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["languages"],
    "additionalProperties": False,
}


def fetch_supported_languages(client: OpenAIClient) -> list[LanguageInfo]:
    """Získa zoznam podporovaných jazykov cez OpenAI a uloží ho do cache."""

    prompt = (
        "Zostav JSON so zoznamom prirodzených jazykov, v ktorých dokážeš spoľahlivo "
        "komunikovať. Vráť aspoň 40 jazykov naprieč svetadielmi. Pre každý jazyk "
        "uved' kľúče 'name' (anglický názov), 'code' (ISO 639-1 alebo 639-3, ak "
        "existuje), 'aliases' (alternatívne názvy alebo názvy v slovenčine, použi prázdne "
        "pole ak žiadne nemáš) a 'script' (napr. Latin, Cyrillic). Odpovedz výhradne JSON "
        "objektom so štruktúrou languages=[...]."
    )
    data = client._call_json(prompt, _LANGUAGE_SCHEMA)
    languages: list[LanguageInfo] = []
    if isinstance(data, dict):
        for item in data.get("languages", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            code_raw = item.get("code")
            code = str(code_raw).strip() if isinstance(code_raw, str) and code_raw else None
            aliases_raw = item.get("aliases", [])
            aliases: tuple[str, ...]
            if isinstance(aliases_raw, list):
                aliases = tuple(str(alias).strip() for alias in aliases_raw if str(alias).strip())
            else:
                aliases = ()
            script_raw = item.get("script")
            script = str(script_raw).strip() if isinstance(script_raw, str) and script_raw else None
            languages.append(LanguageInfo(name=name, code=code, aliases=aliases, script=script))
    if not languages:
        raise ValueError("OpenAI nevrátil žiadne jazyky")
    # deduplikuj podľa mena
    dedup: dict[str, LanguageInfo] = {}
    for lang in languages:
        key = lang.name.casefold()
        if key not in dedup:
            dedup[key] = lang
    normalized = sorted(dedup.values(), key=lambda item: item.name.lower())
    save_language_cache(normalized)
    return normalized


def persist_variant(definition: VariantDefinition) -> VariantDefinition:
    """Persist variant definition ensuring a unique slug on disk."""

    slug = definition.slug or slugify(f"{definition.language} {definition.variant_name or ''}")
    adjusted = definition
    if slug != definition.slug:
        adjusted = replace(definition, slug=slug)

    if variant_exists(adjusted.slug):
        if adjusted.language_code:
            candidate = f"{adjusted.slug}-{adjusted.language_code.lower()}"
            if not variant_exists(candidate):
                adjusted = replace(adjusted, slug=candidate)

    if variant_exists(adjusted.slug):
        base = adjusted.slug
        suffix = 2
        while variant_exists(f"{base}-{suffix}"):
            suffix += 1
        adjusted = replace(adjusted, slug=f"{base}-{suffix}")

    save_variant(adjusted)
    return adjusted


def match_language(query: str, languages: Sequence[LanguageInfo]) -> LanguageInfo | None:
    """Pokúsi sa nájsť jazyk z cache podľa mena/aliasu/kódu."""

    norm = query.strip().casefold()
    if not norm:
        return None
    for lang in languages:
        if lang.matches(norm):
            return lang
    # Skús či query je substring mena (napr. "slovak")
    for lang in languages:
        if norm in lang.name.casefold():
            return lang
    return None
