"""MCP Server for ScrabGPT AI Agent.

This module exposes ScrabGPT's game logic tools via Model Context Protocol (MCP).
It wraps the existing tools from mcp_tools.py and provides them as an MCP server
that can be used by AI agents via mcp-use or other MCP clients.

Usage:
    # Run as stdio server (for local integration)
    python -m scrabgpt.ai.mcp_server

    # Or use with mcp-use in Python
    from mcp_use import MCPClient, MCPAgent
    client = MCPClient.from_dict({"mcpServers": {"scrabble": {...}}})
    agent = MCPAgent(llm=llm, client=client)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from . import mcp_tools

log = logging.getLogger("scrabgpt.ai.mcp_server")

# Create MCP server instance
server = Server(
    name="scrabgpt",
    version="0.1.0",
    instructions=(
        "ScrabGPT MCP Server - Provides Scrabble game logic validation, "
        "scoring, and board state tools for AI agents."
    ),
)


# ========== Tool Definitions ==========

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "rules_first_move_must_cover_center": {
        "name": "rules_first_move_must_cover_center",
        "description": "Check if first move covers center square (7,7)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "placements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row": {"type": "integer", "minimum": 0, "maximum": 14},
                            "col": {"type": "integer", "minimum": 0, "maximum": 14},
                            "letter": {"type": "string", "minLength": 1, "maxLength": 1},
                        },
                        "required": ["row", "col", "letter"],
                    },
                    "description": "List of letter placements",
                }
            },
            "required": ["placements"],
        },
    },
    "rules_placements_in_line": {
        "name": "rules_placements_in_line",
        "description": "Check if all placements are in a single line (ACROSS or DOWN)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "placements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row": {"type": "integer"},
                            "col": {"type": "integer"},
                            "letter": {"type": "string"},
                        },
                        "required": ["row", "col", "letter"],
                    },
                }
            },
            "required": ["placements"],
        },
    },
    "rules_connected_to_existing": {
        "name": "rules_connected_to_existing",
        "description": "Check if placements connect to existing letters on board",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_grid": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 15,
                    "maxItems": 15,
                    "description": "15x15 grid as list of strings ('.' for empty)",
                },
                "placements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row": {"type": "integer"},
                            "col": {"type": "integer"},
                            "letter": {"type": "string"},
                        },
                        "required": ["row", "col", "letter"],
                    },
                },
            },
            "required": ["board_grid", "placements"],
        },
    },
    "rules_no_gaps_in_line": {
        "name": "rules_no_gaps_in_line",
        "description": "Check if there are no gaps in the main line formed by placements",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_grid": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 15,
                    "maxItems": 15,
                },
                "placements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row": {"type": "integer"},
                            "col": {"type": "integer"},
                            "letter": {"type": "string"},
                        },
                    },
                },
                "direction": {
                    "type": "string",
                    "enum": ["ACROSS", "DOWN"],
                    "description": "Direction of the line",
                },
            },
            "required": ["board_grid", "placements", "direction"],
        },
    },
    "rules_extract_all_words": {
        "name": "rules_extract_all_words",
        "description": "Extract all words (main + cross-words) formed by the placements",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_grid": {"type": "array", "items": {"type": "string"}},
                "placements": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
            "required": ["board_grid", "placements"],
        },
    },
    "scoring_score_words": {
        "name": "scoring_score_words",
        "description": "Calculate score for words with premium breakdown",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_grid": {"type": "array", "items": {"type": "string"}},
                "premium_grid": {
                    "type": "array",
                    "items": {"type": "array"},
                    "description": "15x15 grid of premium info or null",
                },
                "placements": {"type": "array", "items": {"type": "object"}},
                "words": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "word": {"type": "string"},
                            "cells": {"type": "array", "items": {"type": "array"}},
                        },
                    },
                },
            },
            "required": ["board_grid", "premium_grid", "placements", "words"],
        },
    },
    "get_board_state": {
        "name": "get_board_state",
        "description": "Get current board state as serialized grid",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board": {
                    "type": ["object", "null"],
                    "description": "Board instance (optional, null for empty board)",
                }
            },
        },
    },
    "get_rack_letters": {
        "name": "get_rack_letters",
        "description": "Get available letters on rack",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rack": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of letter strings",
                }
            },
            "required": ["rack"],
        },
    },
    "get_tile_values": {
        "name": "get_tile_values",
        "description": "Get point values for all letters in variant",
        "inputSchema": {
            "type": "object",
            "properties": {
                "variant": {
                    "type": "string",
                    "default": "slovak",
                    "description": "Variant slug (e.g., 'slovak', 'english')",
                }
            },
        },
    },
    "validate_move_legality": {
        "name": "validate_move_legality",
        "description": "Validate complete move legality (combines all rule checks)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_grid": {"type": "array", "items": {"type": "string"}},
                "placements": {"type": "array", "items": {"type": "object"}},
                "is_first_move": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether this is the first move",
                },
            },
            "required": ["board_grid", "placements"],
        },
    },
    "calculate_move_score": {
        "name": "calculate_move_score",
        "description": "Calculate total score for a move (extracts words + scores them)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board_grid": {"type": "array", "items": {"type": "string"}},
                "premium_grid": {"type": "array", "items": {"type": "array"}},
                "placements": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["board_grid", "premium_grid", "placements"],
        },
    },
}


# ========== MCP Server Handlers ==========


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available ScrabGPT tools."""
    tools = []
    for tool_name, schema in TOOL_SCHEMAS.items():
        tools.append(
            Tool(
                name=schema["name"],
                description=schema["description"],
                inputSchema=schema["inputSchema"],
            )
        )
    log.info(f"Listed {len(tools)} tools")
    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls from MCP clients."""
    log.info(f"Tool called: {name} with args: {arguments}")
    
    try:
        # Get the tool function from mcp_tools
        tool_func = mcp_tools.get_tool_function(name)
        
        # Call the tool function (they're all synchronous)
        result = tool_func(**arguments)
        
        # Return result as TextContent
        result_text = json.dumps(result, indent=2)
        
        log.debug(f"Tool {name} result: {result_text[:200]}...")
        
        return [TextContent(type="text", text=result_text)]
    
    except KeyError:
        error_msg = f"Tool not found: {name}"
        log.error(error_msg)
        return [TextContent(type="text", text=json.dumps({"error": error_msg}))]
    
    except Exception as e:
        error_msg = f"Error calling tool {name}: {e}"
        log.exception(error_msg)
        return [
            TextContent(
                type="text",
                text=json.dumps({"error": error_msg, "type": type(e).__name__}),
            )
        ]


# ========== Server Entry Point ==========


async def main():
    """Run the MCP server with stdio transport."""
    log.info("Starting ScrabGPT MCP Server...")
    
    try:
        async with stdio_server() as (read_stream, write_stream):
            log.info("Server running on stdio")
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    except Exception as e:
        log.exception("Server error")
        raise


def run_server():
    """Synchronous entry point for running the server."""
    asyncio.run(main())


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Run server
    run_server()
