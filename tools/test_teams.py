#!/usr/bin/env python3
"""Test team configuration save/load functionality.

Usage:
    poetry run python tools/test_teams.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrabgpt.core.team_config import TeamManager


def main():
    """Test team configuration."""
    print("=" * 60)
    print("Testing Team Configuration System")
    print("=" * 60)
    print()
    
    # Create team manager
    teams_dir = Path.home() / ".scrabgpt" / "teams"
    print(f"Teams directory: {teams_dir}")
    print()
    
    tm = TeamManager()
    
    # Test 1: Save Novita team
    print("TEST 1: Save Novita team")
    print("-" * 40)
    
    novita_models = [
        {"id": "deepseek/deepseek-r1", "name": "DeepSeek R1", "max_tokens": 4096},
        {"id": "qwen/qwen3-32b-fp8", "name": "Qwen3 32B", "max_tokens": 4096},
        {"id": "zai-org/glm-4.5", "name": "GLM 4.5", "max_tokens": 4096},
    ]
    
    team = tm.save_provider_models("novita", novita_models, timeout_seconds=120)
    print(f"✓ Saved team: {team.name}")
    print(f"  Provider: {team.provider}")
    print(f"  Models: {len(team.models)}")
    print(f"  Timeout: {team.timeout_seconds}s")
    print()
    
    # Test 2: Load Novita team
    print("TEST 2: Load Novita team")
    print("-" * 40)
    
    loaded = tm.load_provider_models("novita")
    if loaded:
        models, timeout = loaded
        print(f"✓ Loaded {len(models)} models")
        for model in models:
            print(f"  - {model['id']}: {model['name']}")
        print(f"  Timeout: {timeout}s")
    else:
        print("❌ Failed to load team")
        return 1
    print()
    
    # Test 3: Save OpenRouter team
    print("TEST 3: Save OpenRouter team")
    print("-" * 40)
    
    openrouter_models = [
        {"id": "openai/gpt-4", "name": "GPT-4", "max_tokens": 8000},
        {"id": "anthropic/claude-3-opus", "name": "Claude 3 Opus", "max_tokens": 8000},
    ]
    
    team2 = tm.save_provider_models("openrouter", openrouter_models, timeout_seconds=180)
    print(f"✓ Saved team: {team2.name}")
    print(f"  Provider: {team2.provider}")
    print(f"  Models: {len(team2.models)}")
    print()
    
    # Test 4: List all teams
    print("TEST 4: List all teams")
    print("-" * 40)
    
    all_teams = tm.list_teams()
    print(f"✓ Found {len(all_teams)} teams:")
    for t in all_teams:
        print(f"  - {t.name} ({t.provider}): {len(t.models)} models")
    print()
    
    # Test 5: Verify files exist
    print("TEST 5: Verify JSON files")
    print("-" * 40)
    
    novita_path = tm.get_team_path("novita")
    openrouter_path = tm.get_team_path("openrouter")
    
    print(f"Novita file: {novita_path}")
    print(f"  Exists: {novita_path.exists()}")
    if novita_path.exists():
        print(f"  Size: {novita_path.stat().st_size} bytes")
    
    print(f"OpenRouter file: {openrouter_path}")
    print(f"  Exists: {openrouter_path.exists()}")
    if openrouter_path.exists():
        print(f"  Size: {openrouter_path.stat().st_size} bytes")
    print()
    
    # Test 6: Save and load opponent mode
    print("TEST 6: Save and load opponent mode")
    print("-" * 40)
    
    tm.save_opponent_mode("novita")
    print("✓ Saved opponent mode: novita")
    
    loaded_mode = tm.load_opponent_mode()
    print(f"✓ Loaded opponent mode: {loaded_mode}")
    
    if loaded_mode != "novita":
        print("❌ Mode mismatch!")
        return 1
    
    print()
    print("=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    print()
    print("Summary:")
    print(f"  Teams directory: {teams_dir}")
    print(f"  Config file: {tm.config_file}")
    print()
    print("Team configurations AND opponent mode are now saved!")
    print("They will persist across app restarts.")
    print()
    print("Next steps:")
    print("1. Start ScrabGPT: poetry run scrabgpt")
    print("2. It should automatically:")
    print("   - Load Novita team (3 models)")
    print("   - Set opponent mode to NOVITA")
    print("3. Start a new game")
    print("4. Watch the results table populate!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
