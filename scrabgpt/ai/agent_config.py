"""Agent configuration loading and management.

This module handles parsing, validation, and discovery of .agent configuration files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

from .tool_registry import get_all_tool_names

log = logging.getLogger("scrabgpt.ai.agent_config")


class AgentConfigError(Exception):
    """Raised when agent configuration is invalid."""
    pass


class ToolNotFoundError(Exception):
    """Raised when tool is not registered."""
    pass


def get_default_agents_dir() -> Path:
    """Get path to default agents directory.
    
    Returns:
        Path to agents/ directory in project root
    """
    # Navigate up from this file to project root
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent
    agents_dir = project_root / "agents"
    
    # Create if doesn't exist
    agents_dir.mkdir(exist_ok=True)
    
    return agents_dir


def load_agent_config(agent_file: Path) -> dict[str, Any]:
    """Load and validate agent configuration from .agent file.
    
    Args:
        agent_file: Path to .agent file
    
    Returns:
        Dict with validated configuration
    
    Raises:
        AgentConfigError: If file is invalid or missing required fields
    """
    try:
        with open(agent_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise AgentConfigError(f"Invalid JSON in {agent_file}: {e}") from e
    except Exception as e:
        raise AgentConfigError(f"Failed to load {agent_file}: {e}") from e
    if not isinstance(config, dict):
        raise AgentConfigError(f"Invalid config payload in {agent_file}: expected object")
    config_dict = cast(dict[str, Any], config)
    
    # Validate schema
    validate_agent_schema(config_dict)
    
    # Validate tools exist
    validate_agent_tools(config_dict)
    
    return config_dict


def validate_agent_schema(config: dict[str, Any]) -> None:
    """Validate agent configuration schema.
    
    Args:
        config: Configuration dict
    
    Raises:
        AgentConfigError: If schema is invalid
    """
    required_fields = ["name", "model", "tools"]
    
    for field in required_fields:
        if field not in config:
            raise AgentConfigError(f"Missing required field: {field}")
    
    # Type checks
    if not isinstance(config["name"], str):
        raise AgentConfigError("Field 'name' must be string")
    
    if not isinstance(config["model"], str):
        raise AgentConfigError("Field 'model' must be string")
    
    if not isinstance(config["tools"], list):
        raise AgentConfigError("Field 'tools' must be list")
    
    for tool in config["tools"]:
        if not isinstance(tool, str):
            raise AgentConfigError(f"Tool name must be string, got: {type(tool)}")


def validate_agent_tools(config: dict[str, Any]) -> None:
    """Validate that all tools in config exist in registry.
    
    Args:
        config: Configuration dict with 'tools' field
    
    Raises:
        AgentConfigError: If unknown tools are referenced
    """
    available_tools = set(get_all_tool_names())
    config_tools = set(config["tools"])
    
    unknown_tools = config_tools - available_tools
    
    if unknown_tools:
        unknown_list = ", ".join(sorted(unknown_tools))
        raise AgentConfigError(
            f"Unknown tools in config: {unknown_list}. "
            f"Available tools: {', '.join(sorted(available_tools))}"
        )


def discover_agents(agents_dir: Path) -> list[dict[str, Any]]:
    """Discover all valid .agent files in directory.
    
    Args:
        agents_dir: Directory to search for .agent files
    
    Returns:
        List of valid agent configurations
    """
    agents: list[dict[str, Any]] = []
    
    if not agents_dir.exists():
        log.warning("Agents directory does not exist: %s", agents_dir)
        return agents
    
    for agent_file in agents_dir.glob("*.agent"):
        try:
            config = load_agent_config(agent_file)
            # Add file path for reference
            config["_file_path"] = str(agent_file)
            agents.append(config)
            log.info("Loaded agent: %s from %s", config["name"], agent_file.name)
        except AgentConfigError as e:
            log.warning("Skipping invalid agent file %s: %s", agent_file.name, e)
        except Exception as e:
            log.exception("Failed to load agent file %s: %s", agent_file.name, e)
    
    return agents


def get_agent_by_name(agents: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Find agent configuration by name.
    
    Args:
        agents: List of agent configurations
        name: Agent name to search for
    
    Returns:
        Agent configuration or None if not found
    """
    for agent in agents:
        if agent.get("name") == name:
            return agent
    
    return None


def get_available_tools() -> list[str]:
    """Get list of all available tool names.
    
    Returns:
        List of registered tool names
    """
    return get_all_tool_names()


def get_tool_schema(tool_name: str) -> dict[str, Any]:
    """Get OpenAI function calling schema for a tool.
    
    Args:
        tool_name: Name of the tool
    
    Returns:
        Function schema dict with name, description, and parameters
    
    Raises:
        ToolNotFoundError: If tool not found
    """
    from .tool_registry import get_tool_function
    
    try:
        tool_func = get_tool_function(tool_name)
    except KeyError as e:
        raise ToolNotFoundError(f"Tool not found: {tool_name}") from e
    
    # Build schema from function docstring and annotations
    # TODO: Generate proper OpenAI function schemas with parameters
    # For now, return basic schema
    
    doc = tool_func.__doc__ or "No description"
    description = doc.split("\n")[0].strip()
    
    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {},  # TODO: Extract from function signature
                "required": [],
            },
        },
    }


def build_tool_schemas(tool_names: list[str]) -> list[dict[str, Any]]:
    """Build OpenAI function schemas for list of tools.
    
    Args:
        tool_names: List of tool names to include
    
    Returns:
        List of OpenAI function schemas
    """
    schemas = []
    
    for tool_name in tool_names:
        try:
            schema = get_tool_schema(tool_name)
            schemas.append(schema)
        except ToolNotFoundError:
            log.warning("Skipping unknown tool: %s", tool_name)
    
    return schemas
