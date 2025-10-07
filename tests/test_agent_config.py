"""BDD tests for agent configuration loading and management.

These tests define how .agent files are parsed, validated, and loaded.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    """Temporary directory for .agent files."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    return agents_dir


@pytest.fixture
def valid_agent_config(agents_dir: Path) -> Path:
    """Create a valid .agent configuration file."""
    config = {
        "name": "Full Access Agent",
        "description": "Agent s prístupom ku všetkým nástrojom",
        "model": "gpt-4o",
        "tools": [
            "rules_first_move_must_cover_center",
            "rules_placements_in_line",
            "rules_connected_to_existing",
            "rules_no_gaps_in_line",
            "rules_extract_all_words",
            "scoring_score_words",
            "get_board_state",
            "get_rack_letters",
            "get_premium_squares",
            "get_tile_values",
            "validate_word_slovak",
        ],
    }
    
    agent_file = agents_dir / "full_access.agent"
    agent_file.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    return agent_file


@pytest.fixture
def minimal_agent_config(agents_dir: Path) -> Path:
    """Create minimal agent with limited tools."""
    config = {
        "name": "Minimal Agent",
        "description": "Agent s obmedzenými nástrojmi - len pravidlá",
        "model": "gpt-4o-mini",
        "tools": [
            "rules_placements_in_line",
            "rules_no_gaps_in_line",
            "get_board_state",
            "get_rack_letters",
        ],
    }
    
    agent_file = agents_dir / "minimal.agent"
    agent_file.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    return agent_file


class TestAgentConfigLoading:
    """Test loading and parsing of .agent configuration files."""

    def test_load_agent_config_from_valid_file(
        self, valid_agent_config: Path
    ) -> None:
        """Given: Valid .agent file exists
        When: Loading agent configuration
        Then: Configuration is parsed correctly
        """
        from scrabgpt.ai.agent_config import load_agent_config

        config = load_agent_config(valid_agent_config)
        
        assert config["name"] == "Full Access Agent"
        assert config["model"] == "gpt-4o"
        assert len(config["tools"]) > 0
        assert "rules_first_move_must_cover_center" in config["tools"]

    def test_load_agent_config_validates_required_fields(
        self, agents_dir: Path
    ) -> None:
        """Given: .agent file missing required fields
        When: Loading configuration
        Then: Validation error is raised
        """
        from scrabgpt.ai.agent_config import load_agent_config, AgentConfigError

        incomplete_config = {
            "name": "Incomplete Agent",
            # Missing 'model' and 'tools'
        }
        
        agent_file = agents_dir / "incomplete.agent"
        agent_file.write_text(json.dumps(incomplete_config))
        
        with pytest.raises(AgentConfigError, match="required field"):
            load_agent_config(agent_file)

    def test_load_agent_config_rejects_invalid_json(
        self, agents_dir: Path
    ) -> None:
        """Given: .agent file with invalid JSON
        When: Loading configuration
        Then: Parse error is raised
        """
        from scrabgpt.ai.agent_config import load_agent_config, AgentConfigError

        agent_file = agents_dir / "broken.agent"
        agent_file.write_text("{invalid json")
        
        with pytest.raises(AgentConfigError, match="JSON"):
            load_agent_config(agent_file)

    def test_discover_agents_finds_all_agent_files(
        self, valid_agent_config: Path, minimal_agent_config: Path, agents_dir: Path
    ) -> None:
        """Given: Multiple .agent files in directory
        When: Discovering agents
        Then: All valid agents are found
        """
        from scrabgpt.ai.agent_config import discover_agents

        agents = discover_agents(agents_dir)
        
        assert len(agents) == 2
        agent_names = [a["name"] for a in agents]
        assert "Full Access Agent" in agent_names
        assert "Minimal Agent" in agent_names

    def test_discover_agents_skips_invalid_files(
        self, valid_agent_config: Path, agents_dir: Path
    ) -> None:
        """Given: Directory with valid and invalid .agent files
        When: Discovering agents
        Then: Only valid agents are returned, invalid ones are logged
        """
        from scrabgpt.ai.agent_config import discover_agents

        # Create invalid agent file
        invalid_file = agents_dir / "invalid.agent"
        invalid_file.write_text("{broken")
        
        agents = discover_agents(agents_dir)
        
        # Should only include the valid agent
        assert len(agents) == 1
        assert agents[0]["name"] == "Full Access Agent"

    def test_get_agent_by_name_returns_matching_config(
        self, valid_agent_config: Path, minimal_agent_config: Path, agents_dir: Path
    ) -> None:
        """Given: Multiple agents configured
        When: Getting agent by name
        Then: Matching configuration is returned
        """
        from scrabgpt.ai.agent_config import discover_agents, get_agent_by_name

        agents = discover_agents(agents_dir)
        
        agent = get_agent_by_name(agents, "Minimal Agent")
        
        assert agent is not None
        assert agent["name"] == "Minimal Agent"
        assert agent["model"] == "gpt-4o-mini"

    def test_get_agent_by_name_returns_none_for_missing(
        self, valid_agent_config: Path, agents_dir: Path
    ) -> None:
        """Given: Agents configured
        When: Getting non-existent agent by name
        Then: None is returned
        """
        from scrabgpt.ai.agent_config import discover_agents, get_agent_by_name

        agents = discover_agents(agents_dir)
        
        agent = get_agent_by_name(agents, "Nonexistent Agent")
        
        assert agent is None


class TestAgentConfigValidation:
    """Test validation of agent configuration structure."""

    def test_validate_agent_tools_checks_tool_existence(self) -> None:
        """Given: Agent config with unknown tool names
        When: Validating tools
        Then: Validation error lists unknown tools
        """
        from scrabgpt.ai.agent_config import validate_agent_tools, AgentConfigError

        config = {
            "name": "Test Agent",
            "model": "gpt-4o",
            "tools": [
                "rules_placements_in_line",  # Valid
                "unknown_tool_xyz",  # Invalid
                "another_bad_tool",  # Invalid
            ],
        }
        
        with pytest.raises(AgentConfigError, match="unknown_tool_xyz"):
            validate_agent_tools(config)

    def test_validate_agent_tools_accepts_all_valid_tools(self) -> None:
        """Given: Agent config with all valid tool names
        When: Validating tools
        Then: Validation passes
        """
        from scrabgpt.ai.agent_config import validate_agent_tools

        config = {
            "name": "Test Agent",
            "model": "gpt-4o",
            "tools": [
                "rules_placements_in_line",
                "rules_no_gaps_in_line",
                "get_board_state",
            ],
        }
        
        # Should not raise
        validate_agent_tools(config)

    def test_agent_config_schema_enforces_types(self) -> None:
        """Given: Agent config with wrong types
        When: Validating schema
        Then: Type error is raised
        """
        from scrabgpt.ai.agent_config import validate_agent_schema, AgentConfigError

        config = {
            "name": "Test Agent",
            "model": "gpt-4o",
            "tools": "should_be_list_not_string",  # Wrong type
        }
        
        with pytest.raises(AgentConfigError, match="tools.*list"):
            validate_agent_schema(config)


class TestAgentToolRegistry:
    """Test the registry of available MCP tools."""

    def test_get_available_tools_returns_all_registered_tools(self) -> None:
        """Given: MCP tools registered
        When: Retrieving available tools
        Then: All tool names are returned
        """
        from scrabgpt.ai.agent_config import get_available_tools

        tools = get_available_tools()
        
        # Should include rule tools
        assert "rules_first_move_must_cover_center" in tools
        assert "rules_placements_in_line" in tools
        
        # Should include scoring tools
        assert "scoring_score_words" in tools
        
        # Should include state tools
        assert "get_board_state" in tools
        assert "get_rack_letters" in tools

    def test_get_tool_schema_returns_function_signature(self) -> None:
        """Given: Tool registered in MCP
        When: Getting tool schema
        Then: JSON schema with parameters is returned
        """
        from scrabgpt.ai.agent_config import get_tool_schema

        schema = get_tool_schema("rules_placements_in_line")
        
        assert schema["name"] == "rules_placements_in_line"
        assert "parameters" in schema
        assert "description" in schema

    def test_get_tool_schema_raises_for_unknown_tool(self) -> None:
        """Given: Unknown tool name
        When: Getting tool schema
        Then: Error is raised
        """
        from scrabgpt.ai.agent_config import get_tool_schema, ToolNotFoundError

        with pytest.raises(ToolNotFoundError):
            get_tool_schema("nonexistent_tool")


class TestAgentConfigDefaults:
    """Test default agent configurations shipped with the app."""

    def test_default_agents_directory_exists(self) -> None:
        """Given: Application installed
        When: Checking default agents directory
        Then: Directory exists with .agent files
        """
        from scrabgpt.ai.agent_config import get_default_agents_dir

        agents_dir = get_default_agents_dir()
        
        assert agents_dir.exists()
        assert agents_dir.is_dir()

    def test_default_agents_are_valid(self) -> None:
        """Given: Default .agent files shipped
        When: Loading default agents
        Then: All configs are valid
        """
        from scrabgpt.ai.agent_config import (
            get_default_agents_dir,
            discover_agents,
        )

        agents_dir = get_default_agents_dir()
        agents = discover_agents(agents_dir)
        
        # Should have at least one default agent
        assert len(agents) >= 1
        
        # All should have required fields
        for agent in agents:
            assert "name" in agent
            assert "model" in agent
            assert "tools" in agent
            assert isinstance(agent["tools"], list)
