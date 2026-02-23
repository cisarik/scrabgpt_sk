#!/usr/bin/env python3
"""Smoke test for team/provider persistence.

Usage:
    poetry run python tools/test_teams.py
    poetry run python tools/test_teams.py --real-home

By default, this script uses a temporary workspace and does not touch
real files in ~/.scrabgpt.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrabgpt.core.team_config import TeamManager


def _print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def _print_section(title: str) -> None:
    print("\n" + title)
    print("-" * 40)


def _build_manager(use_real_home: bool) -> tuple[TeamManager, str, tempfile.TemporaryDirectory[str] | None]:
    if use_real_home:
        manager = TeamManager()
        return manager, "real-home", None

    tmp = tempfile.TemporaryDirectory(prefix="scrabgpt_team_test_")
    root = Path(tmp.name)
    manager = TeamManager(
        teams_dir=root / "teams",
        config_file=root / "config.json",
    )
    return manager, str(root), tmp


def run_smoke_checks(tm: TeamManager) -> int:
    _print_section("TEST 1: Save Novita provider models")
    novita_models = [
        {"id": "deepseek/deepseek-r1", "name": "DeepSeek R1", "max_tokens": 4096},
        {"id": "qwen/qwen3-32b-fp8", "name": "Qwen3 32B", "max_tokens": 4096},
        {"id": "zai-org/glm-4.5", "name": "GLM 4.5", "max_tokens": 4096},
    ]

    novita_team = tm.save_provider_models("novita", novita_models, timeout_seconds=120)
    print(f"✓ Saved team: {novita_team.name}")
    print(f"  Provider: {novita_team.provider}")
    print(f"  Model IDs: {len(novita_team.model_ids)}")
    print(f"  Timeout: {novita_team.timeout_seconds}s")

    _print_section("TEST 2: Load Novita provider models")
    loaded_novita = tm.load_provider_models("novita")
    if not loaded_novita:
        print("❌ Failed to load Novita provider models")
        return 1

    novita_ids, novita_timeout = loaded_novita
    print(f"✓ Loaded {len(novita_ids)} model IDs")
    for model_id in novita_ids:
        print(f"  - {model_id}")
    print(f"  Timeout: {novita_timeout}s")

    _print_section("TEST 3: Save OpenRouter provider models")
    openrouter_models = [
        {"id": "openai/gpt-4", "name": "GPT-4", "max_tokens": 8000},
        {"id": "anthropic/claude-3-opus", "name": "Claude 3 Opus", "max_tokens": 8000},
    ]

    openrouter_team = tm.save_provider_models("openrouter", openrouter_models, timeout_seconds=180)
    print(f"✓ Saved team: {openrouter_team.name}")
    print(f"  Provider: {openrouter_team.provider}")
    print(f"  Model IDs: {len(openrouter_team.model_ids)}")

    _print_section("TEST 4: List all teams")
    all_teams = tm.list_teams()
    print(f"✓ Found {len(all_teams)} team file(s):")
    for team in all_teams:
        print(f"  - {team.name} ({team.provider}): {len(team.model_ids)} model IDs")

    _print_section("TEST 5: Verify JSON files")
    novita_path = tm.get_team_path(novita_team.provider, novita_team.name)
    openrouter_path = tm.get_team_path(openrouter_team.provider, openrouter_team.name)

    print(f"Novita file: {novita_path}")
    print(f"  Exists: {novita_path.exists()}")
    if novita_path.exists():
        print(f"  Size: {novita_path.stat().st_size} bytes")

    print(f"OpenRouter file: {openrouter_path}")
    print(f"  Exists: {openrouter_path.exists()}")
    if openrouter_path.exists():
        print(f"  Size: {openrouter_path.stat().st_size} bytes")

    _print_section("TEST 6: Save and load opponent mode")
    tm.save_opponent_mode("novita")
    loaded_mode = tm.load_opponent_mode()

    print("✓ Saved opponent mode: novita")
    print(f"✓ Loaded opponent mode: {loaded_mode}")

    if loaded_mode != "novita":
        print("❌ Mode mismatch")
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test team/provider persistence")
    parser.add_argument(
        "--real-home",
        action="store_true",
        help="Use ~/.scrabgpt paths instead of an isolated temporary directory",
    )
    args = parser.parse_args()

    _print_header("Testing Team Configuration System")

    manager, workspace, temp_ctx = _build_manager(args.real_home)
    try:
        print(f"Workspace: {workspace}")
        print(f"Teams directory: {manager.teams_dir}")
        print(f"Config file: {manager.config_file}")

        rc = run_smoke_checks(manager)

        if rc == 0:
            _print_header("✓ All checks passed")
            print("Summary:")
            print(f"  Teams directory: {manager.teams_dir}")
            print(f"  Config file: {manager.config_file}")
            if not args.real_home:
                print("  Note: Ran in isolated temporary workspace.")
        return rc
    finally:
        if temp_ctx is not None:
            temp_ctx.cleanup()


if __name__ == "__main__":
    sys.exit(main())
