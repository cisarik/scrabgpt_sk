from __future__ import annotations

from pathlib import Path

import scrabgpt.core.variant_store as variant_store


def test_get_active_variant_slug_reads_from_dotenv(monkeypatch) -> None:
    env_path = Path(".env")
    original_env_contents = env_path.read_text(encoding="utf-8") if env_path.exists() else None

    # Remove in-process override so we rely on the value persisted in .env.
    monkeypatch.delenv("SCRABBLE_VARIANT", raising=False)

    env_path.write_text("SCRABBLE_VARIANT=slovak\n", encoding="utf-8")
    previous_env_loaded = getattr(variant_store, "_ENV_LOADED", False)

    try:
        variant_store._ENV_LOADED = False
        slug = variant_store.get_active_variant_slug()
        assert slug == "slovak"
    finally:
        variant_store._ENV_LOADED = previous_env_loaded
        if original_env_contents is None:
            env_path.unlink(missing_ok=True)
        else:
            env_path.write_text(original_env_contents, encoding="utf-8")
