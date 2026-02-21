"""Adapter to convert internal Scrabble tools to Google Vertex AI tools."""

from __future__ import annotations

import logging
from typing import Any, cast

from google.genai import types

from .tool_schemas import TOOL_SCHEMAS
from . import tool_registry

log = logging.getLogger("scrabgpt.ai.tool_adapter")


def get_gemini_tools() -> list[types.Tool]:
    """Convert internal tool schemas to Vertex AI Tool definitions.
    
    Returns:
        List of types.Tool objects ready for Vertex AI.
    """
    function_declarations: list[types.FunctionDeclaration] = []
    
    for _tool_name, schema in TOOL_SCHEMAS.items():
        # Deep copy schema to avoid modifying original
        import copy
        sanitized_schema = copy.deepcopy(schema["inputSchema"])
        
        # Helper to recursively fix types
        def fix_types(obj: Any) -> None:
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


def _enrich_args_with_context(
    name: str,
    args: dict[str, Any],
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Inject live game context for tools that need board/rack/premium data."""
    if not context:
        return dict(args)

    enriched = dict(args)
    board_grid = context.get("board_grid")
    premium_grid = context.get("premium_grid")
    rack_letters = context.get("rack_letters")
    is_first_move = context.get("is_first_move")

    if name == "get_rack_letters" and "rack" not in enriched and isinstance(rack_letters, list):
        enriched["rack"] = rack_letters

    if name in {
        "rules_connected_to_existing",
        "rules_no_gaps_in_line",
        "rules_extract_all_words",
        "validate_move_legality",
        "calculate_move_score",
        "scoring_score_words",
    }:
        if "board_grid" not in enriched and isinstance(board_grid, list):
            enriched["board_grid"] = board_grid

    if name in {"calculate_move_score", "scoring_score_words"}:
        if "premium_grid" not in enriched and isinstance(premium_grid, list):
            enriched["premium_grid"] = premium_grid

    if name == "validate_move_legality":
        if "is_first_move" not in enriched and isinstance(is_first_move, bool):
            enriched["is_first_move"] = is_first_move

    return enriched


def execute_tool(
    name: str,
    args: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a tool by name with arguments.
    
    Args:
        name: Tool name
        args: Tool arguments
        
    Returns:
        Tool result dictionary
    """
    try:
        log.info("Executing tool: %s with args: %s", name, args)
        
        # Fast path: return live state for read-only context tools.
        if name == "get_board_state" and context is not None:
            board_grid = context.get("board_grid")
            blanks = context.get("blanks")
            if isinstance(board_grid, list):
                return {
                    "grid": board_grid,
                    "blanks": blanks if isinstance(blanks, list) else [],
                    "source": "live_game_state",
                }

        if name == "get_premium_squares" and context is not None:
            premium_squares = context.get("premium_squares")
            if isinstance(premium_squares, list):
                return {
                    "premiums": premium_squares,
                    "source": "live_game_state",
                }

        # Case-insensitive lookup
        try:
            tool_func = tool_registry.get_tool_function(name)
        except KeyError:
            # Try to find case-insensitive match
            all_tools = tool_registry.ALL_TOOLS
            lower_name = name.lower()
            found_name = next((k for k in all_tools.keys() if k.lower() == lower_name), None)
            
            if found_name:
                log.info("Case mismatch: requested '%s', found '%s'", name, found_name)
                tool_func = tool_registry.get_tool_function(found_name)
            else:
                raise

        enriched_args = _enrich_args_with_context(name, args, context)
        result = tool_func(**enriched_args)
        if isinstance(result, dict):
            return cast(dict[str, Any], result)
        return {"result": result}
    except Exception as e:
        log.exception("Error executing tool %s", name)
        return {"error": str(e)}
