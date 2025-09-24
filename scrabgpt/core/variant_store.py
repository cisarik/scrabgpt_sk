from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .assets import get_assets_path

log = logging.getLogger("scrabgpt.variants")

_VARIANTS_SUBDIR = "variants"
_DEFAULT_VARIANT_SLUG = "english"
_ROOT_DIR = Path(__file__).resolve().parents[2]
_ENV_PATH = _ROOT_DIR / ".env"
_ENV_LOADED = False


@dataclass(frozen=True)
class VariantLetter:
    """Jedna dlaždica (písmeno alebo blank) v Scrabble variante."""

    letter: str
    count: int
    points: int


@dataclass(frozen=True)
class VariantDefinition:
    """Definícia Scrabble variantu vrátane distribúcie a bodov."""

    slug: str
    language: str
    letters: tuple[VariantLetter, ...]
    source: str = "openai"
    fetched_at: str | None = None

    @property
    def distribution(self) -> dict[str, int]:
        return {letter.letter: letter.count for letter in self.letters}

    @property
    def tile_points(self) -> dict[str, int]:
        return {letter.letter: letter.points for letter in self.letters}

    @property
    def total_tiles(self) -> int:
        return sum(letter.count for letter in self.letters)


# --- Interné helpery -----------------------------------------------------


def _variants_dir() -> Path:
    path = get_assets_path() / _VARIANTS_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _variant_path(slug: str) -> Path:
    slug_norm = slugify(slug)
    return _variants_dir() / f"{slug_norm}.json"


def _ensure_env_loaded() -> None:
    """Ensure values from .env are present in the process environment."""

    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from dotenv import load_dotenv
    except Exception:  # python-dotenv is an optional dependency in some contexts
        _ENV_LOADED = True
        return

    try:
        if _ENV_PATH.exists():
            load_dotenv(_ENV_PATH, override=False)
        else:
            # Fall back to default search to support alternate layouts during tests
            load_dotenv(override=False)
    except Exception:
        # Loading .env is a best-effort; missing or malformed files should not crash startup
        pass
    finally:
        _ENV_LOADED = True


def slugify(text: str) -> str:
    """Vytvorí slug (lowercase, bez diakritiky) pre názov variantu."""

    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in ascii_only.lower())
    cleaned = "-".join(filter(None, cleaned.split("-")))
    return cleaned or "variant"


def _coerce_int(value: object) -> int:
    """Convert JSON-loaded numeric values into ints with validation."""

    if value is None or isinstance(value, bool):
        raise TypeError("numeric value missing")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"expected integer, got {value}")
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("empty string cannot be converted to int")
        return int(stripped)
    raise TypeError(f"unsupported numeric value: {value!r}")


def _load_variant_from_path(path: Path) -> VariantDefinition:
    data = json.loads(path.read_text(encoding="utf-8"))
    language = str(data.get("language") or data.get("name") or "Unknown")
    slug = slugify(str(data.get("slug") or path.stem))
    source = str(data.get("source", "openai"))
    fetched_at = data.get("fetched_at")
    letters_raw: Iterable[dict[str, object]] = data.get("letters", [])

    letters: list[VariantLetter] = []
    seen: set[str] = set()
    for idx, raw in enumerate(letters_raw):
        if not isinstance(raw, dict):
            log.warning("variant_skip_invalid_letter path=%s index=%s", path, idx)
            continue
        letter = normalise_letter(str(raw.get("letter", "")).strip())
        if not letter:
            log.warning("variant_letter_missing path=%s index=%s", path, idx)
            continue
        if letter in seen:
            log.warning("variant_letter_duplicate path=%s letter=%s", path, letter)
            continue
        if letter != "?" and len(letter) != 1:
            log.warning(
                "variant_letter_multichar path=%s letter=%s len=%s",
                path,
                letter,
                len(letter),
            )
            continue
        try:
            count = _coerce_int(raw.get("count"))
            points = _coerce_int(raw.get("points"))
        except (TypeError, ValueError):
            log.warning("variant_letter_bad_numeric path=%s letter=%s", path, letter)
            continue
        letters.append(VariantLetter(letter=letter, count=count, points=points))
        seen.add(letter)

    if not letters:
        raise ValueError(f"Variant {path} neobsahuje žiadne dlaždice")

    return VariantDefinition(
        slug=slug,
        language=language,
        letters=tuple(sorted(letters, key=lambda letter: letter.letter)),
        source=source,
        fetched_at=str(fetched_at) if fetched_at else None,
    )


def normalise_letter(letter: str) -> str:
    if not letter:
        return ""
    upper = letter.upper()
    if upper in {"ŽOLÍK", "JOKER", "BLANK", "WILDCARD", "WILD", "JOKER", "BLANK TILE"}:
        return "?"
    if upper in {"?", "\u2047"}:
        return "?"
    upper = upper.replace(" ", "")
    return upper


# --- Built-in variant (angličtina) ---------------------------------------

_BUILTIN_ENGLISH_DATA = {
    "language": "English",
    "slug": _DEFAULT_VARIANT_SLUG,
    "source": "builtin",
    "fetched_at": datetime.utcnow().isoformat(timespec="seconds"),
    "letters": [
        {"letter": "?", "count": 2, "points": 0},
        {"letter": "A", "count": 9, "points": 1},
        {"letter": "B", "count": 2, "points": 3},
        {"letter": "C", "count": 2, "points": 3},
        {"letter": "D", "count": 4, "points": 2},
        {"letter": "E", "count": 12, "points": 1},
        {"letter": "F", "count": 2, "points": 4},
        {"letter": "G", "count": 3, "points": 2},
        {"letter": "H", "count": 2, "points": 4},
        {"letter": "I", "count": 9, "points": 1},
        {"letter": "J", "count": 1, "points": 8},
        {"letter": "K", "count": 1, "points": 5},
        {"letter": "L", "count": 4, "points": 1},
        {"letter": "M", "count": 2, "points": 3},
        {"letter": "N", "count": 6, "points": 1},
        {"letter": "O", "count": 8, "points": 1},
        {"letter": "P", "count": 2, "points": 3},
        {"letter": "Q", "count": 1, "points": 10},
        {"letter": "R", "count": 6, "points": 1},
        {"letter": "S", "count": 4, "points": 1},
        {"letter": "T", "count": 6, "points": 1},
        {"letter": "U", "count": 4, "points": 1},
        {"letter": "V", "count": 2, "points": 4},
        {"letter": "W", "count": 2, "points": 4},
        {"letter": "X", "count": 1, "points": 8},
        {"letter": "Y", "count": 2, "points": 4},
        {"letter": "Z", "count": 1, "points": 10},
    ],
}


def ensure_builtin_variant() -> None:
    """Zabezpečí, že predvolený variant je uložený na disku."""

    path = _variant_path(_DEFAULT_VARIANT_SLUG)
    if path.exists():
        return
    log.info("creating_builtin_variant path=%s", path)
    payload = dict(_BUILTIN_ENGLISH_DATA)
    payload["fetched_at"] = datetime.utcnow().isoformat(timespec="seconds")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# --- Verejné API ----------------------------------------------------------


def list_installed_variants() -> list[VariantDefinition]:
    ensure_builtin_variant()
    variants: list[VariantDefinition] = []
    for path in sorted(_variants_dir().glob("*.json")):
        try:
            variants.append(_load_variant_from_path(path))
        except Exception as exc:  # noqa: BLE001
            log.error("variant_load_failed path=%s error=%s", path, exc)
    return variants


def variant_exists(slug: str) -> bool:
    return _variant_path(slug).exists()


def load_variant(slug: str) -> VariantDefinition:
    ensure_builtin_variant()
    path = _variant_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"Variant '{slug}' neexistuje")
    return _load_variant_from_path(path)


def save_variant(defn: VariantDefinition) -> Path:
    ensure_builtin_variant()
    payload = {
        "language": defn.language,
        "slug": defn.slug,
        "source": defn.source,
        "fetched_at": defn.fetched_at or datetime.utcnow().isoformat(timespec="seconds"),
        "letters": [
            {"letter": letter.letter, "count": letter.count, "points": letter.points}
            for letter in defn.letters
        ],
    }
    path = _variant_path(defn.slug)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def get_active_variant_slug() -> str:
    ensure_builtin_variant()
    _ensure_env_loaded()
    slug = slugify(Path(_variant_path(_DEFAULT_VARIANT_SLUG)).stem)
    from os import getenv

    candidate = getenv("SCRABBLE_VARIANT", slug)
    path = _variant_path(candidate)
    if path.exists():
        return slugify(candidate)
    log.warning("active_variant_missing slug=%s -> fallback=%s", candidate, slug)
    return slug


def set_active_variant_slug(slug: str) -> VariantDefinition:
    ensure_builtin_variant()
    _ensure_env_loaded()
    definition = load_variant(slug)
    from os import environ

    environ["SCRABBLE_VARIANT"] = definition.slug

    try:
        from dotenv import set_key as _dotenv_set_key
    except Exception:
        return definition

    try:
        _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not _ENV_PATH.exists():
            _ENV_PATH.touch()
        _dotenv_set_key(str(_ENV_PATH), "SCRABBLE_VARIANT", definition.slug)
    except Exception:
        # Persisting to .env is best-effort; runtime environment already reflects the change.
        pass
    return definition


def get_active_variant() -> VariantDefinition:
    return load_variant(get_active_variant_slug())
