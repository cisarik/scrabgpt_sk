#!/usr/bin/env python
"""Quick test to verify opponent mode UI integration."""

import sys
from PySide6.QtWidgets import QApplication
from scrabgpt.ui.settings_dialog import SettingsDialog
from scrabgpt.ai.agent_config import discover_agents, get_default_agents_dir
from scrabgpt.core.opponent_mode import OpponentMode

def test_settings_dialog():
    """Test that settings dialog opens and works."""
    app = QApplication(sys.argv)
    
    # Load agents
    agents = discover_agents(get_default_agents_dir())
    print(f"Loaded {len(agents)} agents:")
    for agent in agents:
        print(f"  - {agent['name']} ({len(agent['tools'])} tools)")
    
    # Create dialog
    dialog = SettingsDialog(
        current_mode=OpponentMode.BEST_MODEL,
        current_agent_name=None,
        available_agents=agents,
        game_in_progress=False,
    )
    
    print("\nOpening Settings Dialog...")
    print("Available modes:")
    for mode in OpponentMode:
        if mode.is_available:
            print(f"  ✓ {mode.display_name_sk}: {mode.description_sk}")
        else:
            print(f"  ✗ {mode.display_name_sk}: {mode.description_sk} (disabled)")
    
    # Show dialog
    result = dialog.exec()
    
    if result:
        selected_mode = dialog.get_selected_mode()
        selected_agent = dialog.get_selected_agent_name()
        
        print(f"\n✓ Settings accepted!")
        print(f"  Mode: {selected_mode.display_name_sk} ({selected_mode.value})")
        if selected_mode == OpponentMode.AGENT and selected_agent:
            print(f"  Agent: {selected_agent}")
    else:
        print("\n✗ Settings cancelled")
    
    return result

if __name__ == "__main__":
    test_settings_dialog()
