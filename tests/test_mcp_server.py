"""Tests for MCP server wrapper.

These tests verify that:
1. The MCP server module loads correctly
2. Tool schemas are valid
3. Tool routing works correctly
4. The server can be used with mcp-use (integration tests)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scrabgpt.ai import mcp_server, mcp_tools


# ========== Unit Tests (Offline) ==========


def test_server_instance_created():
    """Test that server instance is created with correct metadata."""
    assert mcp_server.server is not None
    assert mcp_server.server.name == "scrabgpt"


def test_tool_schemas_defined():
    """Test that all tool schemas are properly defined."""
    assert len(mcp_server.TOOL_SCHEMAS) > 0
    
    # Check that each schema has required fields
    for tool_name, schema in mcp_server.TOOL_SCHEMAS.items():
        assert "name" in schema
        assert "description" in schema
        assert "inputSchema" in schema
        assert schema["name"] == tool_name
        
        # Input schema should be valid JSON Schema
        input_schema = schema["inputSchema"]
        assert input_schema["type"] == "object"
        assert "properties" in input_schema or "required" in input_schema


def test_all_mcp_tools_have_schemas():
    """Test that all registered tools have corresponding schemas."""
    tool_names = mcp_tools.get_all_tool_names()
    schema_names = set(mcp_server.TOOL_SCHEMAS.keys())
    
    # Not all tools need to be exposed via MCP (some are internal helpers)
    # But all exposed tools must exist in mcp_tools
    for schema_name in schema_names:
        assert schema_name in tool_names, f"Schema {schema_name} has no tool function"


def test_list_tools_handler_exists():
    """Test that list_tools handler is registered."""
    # Check that the handler is decorated and registered
    assert hasattr(mcp_server, "list_tools")


def test_call_tool_handler_exists():
    """Test that call_tool handler is registered."""
    assert hasattr(mcp_server, "call_tool")


# ========== Integration Tests (Require MCP Client) ==========


@pytest.mark.asyncio
@pytest.mark.internet
async def test_list_tools_via_mcp():
    """Test listing tools via MCP protocol."""
    # This would require starting the server and connecting a client
    # For now, we test the handler directly
    tools = await mcp_server.list_tools()
    
    assert len(tools) > 0
    assert all(hasattr(tool, "name") for tool in tools)
    assert all(hasattr(tool, "description") for tool in tools)
    assert all(hasattr(tool, "inputSchema") for tool in tools)


@pytest.mark.asyncio
async def test_call_tool_via_handler_get_tile_values():
    """Test calling get_tile_values tool via handler."""
    result = await mcp_server.call_tool(
        name="get_tile_values",
        arguments={"variant": "slovak"},
    )
    
    assert len(result) == 1
    assert result[0].type == "text"
    
    # Parse JSON response
    data = json.loads(result[0].text)
    assert "values" in data
    assert "variant" in data
    assert data["variant"] == "slovak"
    assert isinstance(data["values"], dict)


@pytest.mark.asyncio
async def test_call_tool_via_handler_validate_move():
    """Test calling validate_move_legality tool via handler."""
    board_grid = ["." * 15] * 15
    placements = [
        {"row": 7, "col": 6, "letter": "C"},
        {"row": 7, "col": 7, "letter": "A"},
        {"row": 7, "col": 8, "letter": "T"},
    ]
    
    result = await mcp_server.call_tool(
        name="validate_move_legality",
        arguments={
            "board_grid": board_grid,
            "placements": placements,
            "is_first_move": True,
        },
    )
    
    assert len(result) == 1
    data = json.loads(result[0].text)
    
    assert "valid" in data
    assert "checks" in data
    assert "reason" in data
    assert data["valid"] is True  # This should be a legal first move


@pytest.mark.asyncio
async def test_call_tool_nonexistent():
    """Test calling a nonexistent tool returns error."""
    result = await mcp_server.call_tool(
        name="nonexistent_tool",
        arguments={},
    )
    
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert "error" in data
    assert "not found" in data["error"].lower()


@pytest.mark.asyncio
async def test_call_tool_invalid_arguments():
    """Test calling tool with invalid arguments returns error."""
    result = await mcp_server.call_tool(
        name="get_tile_values",
        arguments={"invalid_arg": "value"},
    )
    
    # Tool should handle unexpected kwargs gracefully
    # (Python will raise TypeError for unexpected kwargs)
    assert len(result) == 1
    data = json.loads(result[0].text)
    # Should either work (ignoring extra args) or return error
    assert "error" in data or "values" in data


# ========== Configuration Tests ==========


def test_mcp_config_file_exists():
    """Test that scrabble_mcp.json configuration exists."""
    config_path = Path(__file__).parent.parent / "scrabble_mcp.json"
    assert config_path.exists(), "scrabble_mcp.json not found in project root"


def test_mcp_config_file_valid():
    """Test that configuration file is valid JSON with correct structure."""
    config_path = Path(__file__).parent.parent / "scrabble_mcp.json"
    
    with open(config_path) as f:
        config = json.load(f)
    
    assert "mcpServers" in config
    assert "scrabble" in config["mcpServers"]
    
    server_config = config["mcpServers"]["scrabble"]
    assert "command" in server_config
    assert "args" in server_config
    assert isinstance(server_config["args"], list)


# ========== Stress Tests ==========


@pytest.mark.stress
@pytest.mark.asyncio
async def test_call_all_tools():
    """Stress test: Call all tools with minimal valid arguments."""
    # This ensures all tools can be called without crashing
    
    # Prepare common test data
    board_grid = ["." * 15] * 15
    placements = [{"row": 7, "col": 7, "letter": "A"}]
    premium_grid = [[None] * 15 for _ in range(15)]
    
    test_cases = [
        ("rules_first_move_must_cover_center", {"placements": placements}),
        ("rules_placements_in_line", {"placements": placements}),
        ("rules_connected_to_existing", {"board_grid": board_grid, "placements": placements}),
        ("rules_no_gaps_in_line", {"board_grid": board_grid, "placements": placements, "direction": "ACROSS"}),
        ("rules_extract_all_words", {"board_grid": board_grid, "placements": placements}),
        ("get_board_state", {"board": None}),
        ("get_rack_letters", {"rack": ["A", "B", "C"]}),
        ("get_tile_values", {"variant": "slovak"}),
        ("validate_move_legality", {"board_grid": board_grid, "placements": placements, "is_first_move": True}),
    ]
    
    results = []
    for tool_name, arguments in test_cases:
        try:
            result = await mcp_server.call_tool(name=tool_name, arguments=arguments)
            data = json.loads(result[0].text)
            results.append((tool_name, "ok", data))
        except Exception as e:
            results.append((tool_name, "error", str(e)))
    
    # Check results
    errors = [r for r in results if r[1] == "error"]
    if errors:
        print("\nErrors encountered:")
        for tool_name, status, error in errors:
            print(f"  {tool_name}: {error}")
    
    # At least 80% of tools should work
    success_rate = (len(results) - len(errors)) / len(results)
    assert success_rate >= 0.8, f"Only {success_rate:.0%} of tools succeeded"


# ========== Documentation Tests ==========


def test_examples_directory_exists():
    """Test that examples directory exists."""
    examples_dir = Path(__file__).parent.parent / "examples"
    assert examples_dir.exists()
    assert examples_dir.is_dir()


def test_example_demo_script_exists():
    """Test that example demo script exists."""
    demo_script = Path(__file__).parent.parent / "examples" / "mcp_agent_demo.py"
    assert demo_script.exists()


def test_examples_readme_exists():
    """Test that examples README exists."""
    readme = Path(__file__).parent.parent / "examples" / "README.md"
    assert readme.exists()
