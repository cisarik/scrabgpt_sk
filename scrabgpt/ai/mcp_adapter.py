"""Adapter to convert MCP tools to Google Vertex AI tools."""

from __future__ import annotations

import logging
from typing import Any, Callable

from google.genai import types

from .mcp_server import TOOL_SCHEMAS
from . import mcp_tools

log = logging.getLogger("scrabgpt.ai.mcp_adapter")


def get_gemini_tools() -> list[types.Tool]:
    """Convert MCP tool schemas to Vertex AI Tool definitions.
    
    Returns:
        List of types.Tool objects ready for Vertex AI.
    """
    function_declarations = []
    
    for tool_name, schema in TOOL_SCHEMAS.items():
        # Deep copy schema to avoid modifying original
        import copy
        sanitized_schema = copy.deepcopy(schema["inputSchema"])
        
        # Helper to recursively fix types
        def fix_types(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "type":
                        # Fix ["object", "null"] -> "OBJECT"
                        if isinstance(v, list):
                            if "object" in v:
                                obj[k] = "OBJECT"
                            elif "string" in v:
                                obj[k] = "STRING"
                            elif "integer" in v:
                                obj[k] = "INTEGER"
                            elif "number" in v:
                                obj[k] = "NUMBER"
                            elif "boolean" in v:
                                obj[k] = "BOOLEAN"
                            elif "array" in v:
                                obj[k] = "ARRAY"
                            else:
                                obj[k] = "STRING" # Fallback
                        # Fix lowercase types to uppercase for Vertex (though SDK might handle it, let's be safe)
                        elif isinstance(v, str):
                            obj[k] = v.upper()
                    else:
                        fix_types(v)
            elif isinstance(obj, list):
                for item in obj:
                    fix_types(item)

        fix_types(sanitized_schema)

        func_decl = types.FunctionDeclaration(
            name=schema["name"],
            description=schema["description"],
            parameters=sanitized_schema,
        )
        function_declarations.append(func_decl)
        
    return [types.Tool(function_declarations=function_declarations)]


def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool by name with arguments.
    
    Args:
        name: Tool name
        args: Tool arguments
        
    Returns:
        Tool result dictionary
    """
    try:
        log.info("Executing tool: %s with args: %s", name, args)
        
        # Case-insensitive lookup
        try:
            tool_func = mcp_tools.get_tool_function(name)
        except KeyError:
            # Try to find case-insensitive match
            all_tools = mcp_tools.ALL_TOOLS
            lower_name = name.lower()
            found_name = next((k for k in all_tools.keys() if k.lower() == lower_name), None)
            
            if found_name:
                log.info("Case mismatch: requested '%s', found '%s'", name, found_name)
                tool_func = mcp_tools.get_tool_function(found_name)
            else:
                raise

        result = tool_func(**args)
        return result
    except Exception as e:
        log.exception("Error executing tool %s", name)
        return {"error": str(e)}
