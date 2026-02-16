"""AI agent player using local Scrabble tools.

NOTE: This is a STUB implementation. Full integration requires:
1. OpenAI function calling integration
2. Iterative tool call loop
3. Error handling and retry logic
"""

from __future__ import annotations

import logging
from typing import Any, cast

from ..core.board import Board
from ..core.variant_store import VariantDefinition
from .agent_config import build_tool_schemas


log = logging.getLogger("scrabgpt.ai.agent_player")


class ToolNotAvailableError(Exception):
    """Raised when agent tries to use unavailable tool."""
    pass


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""
    pass


class ToolExecutor:
    """Executor for local tools with access control.
    
    This class wraps tool functions and enforces that agents can only
    call tools they're configured to use.
    """
    
    def __init__(self, available_tools: list[str]) -> None:
        """Initialize executor with allowed tools.
        
        Args:
            available_tools: List of tool names this agent can use
        """
        self.available_tools = set(available_tools)
        log.info("Initialized tool executor with %d tools", len(available_tools))
    
    async def execute_tool(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a tool function.
        
        Args:
            tool_name: Name of tool to execute
            **kwargs: Tool-specific parameters
        
        Returns:
            Tool result as dict
        
        Raises:
            ToolNotAvailableError: If tool not in agent's allowed list
            ToolExecutionError: If tool execution fails
        """
        if tool_name not in self.available_tools:
            raise ToolNotAvailableError(
                f"Tool '{tool_name}' not available to this agent. "
                f"Available tools: {', '.join(sorted(self.available_tools))}"
            )
        
        try:
            from .tool_registry import get_tool_function
            
            tool_func = get_tool_function(tool_name)
            result = tool_func(**kwargs)
            
            log.debug("Tool %s executed successfully", tool_name)
            return cast(dict[str, Any], result)
        
        except Exception as e:
            log.exception("Tool %s execution failed: %s", tool_name, e)
            raise ToolExecutionError(f"Tool execution failed: {e}") from e


async def propose_move_agent(
    agent_config: dict[str, Any],
    board: Board,
    rack: list[str],
    variant: VariantDefinition,
    max_iterations: int = 10,
) -> dict[str, Any]:
    """Propose move using AI agent with local Scrabble tools.
    
    This is a STUB implementation. Full implementation requires:
    1. OpenAI function calling loop
    2. Tool call handling
    3. State management across calls
    4. Validation and retry logic
    
    Args:
        agent_config: Agent configuration with model and tools
        board: Current board state
        rack: Available letters
        variant: Game variant
        max_iterations: Max tool call iterations
    
    Returns:
        Move dict with placements
    
    Raises:
        NotImplementedError: This is a stub
    """
    log.warning("propose_move_agent is STUB ONLY - not functional yet")
    
    # Initialize tool executor
    executor = ToolExecutor(agent_config["tools"])
    
    # Build OpenAI function schemas
    tool_schemas = build_tool_schemas_for_agent(agent_config)
    
    # Build system prompt
    system_prompt = build_agent_system_prompt(agent_config)
    
    # Build context
    context = build_agent_context(board, rack, variant)
    
    log.debug(
        "Prepared agent scaffolding: %d tools, %d schemas, prompt=%d chars, context=%d chars",
        len(executor.available_tools),
        len(tool_schemas),
        len(system_prompt),
        len(context),
    )
    
    # TODO: Implement OpenAI function calling loop
    # 1. Call OpenAI with tools
    # 2. Handle tool_calls in response
    # 3. Execute tools via executor
    # 4. Feed results back to OpenAI
    # 5. Repeat until final answer
    # 6. Parse and return move
    
    raise NotImplementedError(
        "Agent player requires full tool integration with OpenAI function calling. "
        "Please implement the tool calling loop."
    )


# Backward compatibility alias for older tests/imports.
MCPToolExecutor = ToolExecutor


def build_tool_schemas_for_agent(agent_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Build OpenAI tool schemas for agent's configured tools.
    
    Args:
        agent_config: Agent configuration
    
    Returns:
        List of OpenAI function schemas
    """
    return build_tool_schemas(agent_config["tools"])


def build_agent_system_prompt(agent_config: dict[str, Any]) -> str:
    """Build system prompt for agent.
    
    Args:
        agent_config: Agent configuration
    
    Returns:
        System prompt string
    """
    tools_list = "\n".join(f"- {tool}" for tool in agent_config["tools"])
    
    prompt = f"""Si expert na Scrabble. Tvoja úloha je navrhnúť najlepší možný ťah v hre.

Máš k dispozícii tieto nástroje (tools):
{tools_list}

Použi nástroje na:
1. Zistenie stavu hracej dosky a dostupných písmen
2. Overenie platnosti navrhovaných ťahov
3. Výpočet bodov pre rôzne možnosti
4. Validáciu slov v slovníku

Postupuj systematicky:
1. Preskúmaj hraciu dosku a rack
2. Uvažuj nad možnými ťahmi
3. Validuj každý ťah pomocou nástrojov
4. Vyber ťah s najvyšším bodovým ziskom

Vráť finálny ťah vo formáte JSON:
{{
  "placements": [{{"row": int, "col": int, "letter": str}}, ...],
  "start": {{"row": int, "col": int}},
  "direction": "ACROSS" | "DOWN",
  "word": str
}}
"""
    
    return prompt


def build_agent_context(
    board: Board,
    rack: list[str],
    variant: VariantDefinition,
) -> str:
    """Build context string for agent with current game state.
    
    Args:
        board: Current board
        rack: Available letters
        variant: Game variant
    
    Returns:
        Context string for AI
    """
    # Serialize board
    grid = []
    for r in range(15):
        row_chars = []
        for c in range(15):
            letter = board.cells[r][c].letter
            row_chars.append(letter if letter else ".")
        grid.append("".join(row_chars))
    
    grid_str = "\n".join(grid)
    rack_str = "".join(rack)
    
    context = f"""Aktuálny stav hry:

Hracia doska (15x15):
{grid_str}

Tvoj rack: {rack_str}

Variant: {variant.language}

Navrhni najlepší ťah pomocou dostupných nástrojov.
"""
    
    return context
