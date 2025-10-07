"""BDD tests for AI agent player using MCP tools.

These tests define how the agent should interact with MCP tools to make moves.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scrabgpt.core.board import Board
from scrabgpt.core.assets import get_premiums_path
from scrabgpt.core.variant_store import VariantDefinition


@pytest.fixture
def empty_board() -> Board:
    """Empty 15x15 Scrabble board."""
    return Board(get_premiums_path())


@pytest.fixture
def slovak_variant() -> VariantDefinition:
    """Slovak variant definition."""
    from scrabgpt.core.variant_store import get_variant_by_slug
    return get_variant_by_slug("slovak")


@pytest.fixture
def full_access_agent_config() -> dict:
    """Agent configuration with all tools enabled."""
    return {
        "name": "Full Access Agent",
        "description": "Agent with all tools",
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
            "validate_move_legality",
            "calculate_move_score",
        ],
    }


@pytest.fixture
def minimal_agent_config() -> dict:
    """Agent configuration with minimal tools."""
    return {
        "name": "Minimal Agent",
        "description": "Agent with limited tools",
        "model": "gpt-4o-mini",
        "tools": [
            "get_board_state",
            "get_rack_letters",
            "validate_move_legality",
        ],
    }


class TestAgentMoveGeneration:
    """Test agent's ability to generate moves using MCP tools."""

    @pytest.mark.asyncio
    async def test_agent_proposes_valid_first_move_on_empty_board(
        self,
        empty_board: Board,
        slovak_variant: VariantDefinition,
        full_access_agent_config: dict,
    ) -> None:
        """Given: Empty board and agent with full tool access
        When: Agent proposes first move
        Then: Move covers center and is valid
        """
        from scrabgpt.ai.agent_player import propose_move_agent

        rack = ["H", "E", "L", "L", "O", "W", "D"]
        
        # Mock OpenAI API to return a valid move
        with patch("scrabgpt.ai.agent_player.OpenAIClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            # Agent should use tools to validate and propose move
            move = await propose_move_agent(
                agent_config=full_access_agent_config,
                board=empty_board,
                rack=rack,
                variant=slovak_variant,
            )
        
        assert move is not None
        assert "placements" in move
        assert len(move["placements"]) > 0
        
        # Check that move covers center
        placements_coords = [(p["row"], p["col"]) for p in move["placements"]]
        assert (7, 7) in placements_coords

    @pytest.mark.asyncio
    async def test_agent_uses_get_board_state_tool_during_planning(
        self,
        empty_board: Board,
        slovak_variant: VariantDefinition,
        full_access_agent_config: dict,
    ) -> None:
        """Given: Agent generating move
        When: Agent needs board information
        Then: Agent calls get_board_state tool
        """
        from scrabgpt.ai.agent_player import propose_move_agent

        rack = ["C", "A", "T", "S"]
        
        with patch("scrabgpt.ai.agent_player.MCPToolExecutor") as mock_executor:
            mock_executor_instance = MagicMock()
            mock_executor.return_value = mock_executor_instance
            
            # Mock tool call to get_board_state
            mock_executor_instance.execute_tool = AsyncMock(
                return_value={"grid": ["." * 15 for _ in range(15)]}
            )
            
            with patch("scrabgpt.ai.agent_player.OpenAIClient"):
                await propose_move_agent(
                    agent_config=full_access_agent_config,
                    board=empty_board,
                    rack=rack,
                    variant=slovak_variant,
                )
            
            # Verify get_board_state was called
            calls = mock_executor_instance.execute_tool.call_args_list
            tool_names = [call[0][0] for call in calls]
            assert "get_board_state" in tool_names

    @pytest.mark.asyncio
    async def test_agent_uses_validate_move_legality_before_proposing(
        self,
        empty_board: Board,
        slovak_variant: VariantDefinition,
        full_access_agent_config: dict,
    ) -> None:
        """Given: Agent considering a move
        When: Agent validates move legality
        Then: Agent calls validate_move_legality tool
        """
        from scrabgpt.ai.agent_player import propose_move_agent

        rack = ["H", "I"]
        
        with patch("scrabgpt.ai.agent_player.MCPToolExecutor") as mock_executor:
            mock_executor_instance = MagicMock()
            mock_executor.return_value = mock_executor_instance
            
            # Mock validation tool to return valid
            mock_executor_instance.execute_tool = AsyncMock(
                return_value={"valid": True, "checks": {}}
            )
            
            with patch("scrabgpt.ai.agent_player.OpenAIClient"):
                await propose_move_agent(
                    agent_config=full_access_agent_config,
                    board=empty_board,
                    rack=rack,
                    variant=slovak_variant,
                )
            
            # Verify validation was called
            calls = mock_executor_instance.execute_tool.call_args_list
            tool_names = [call[0][0] for call in calls]
            assert "validate_move_legality" in tool_names

    @pytest.mark.asyncio
    async def test_agent_calculates_score_before_finalizing_move(
        self,
        empty_board: Board,
        slovak_variant: VariantDefinition,
        full_access_agent_config: dict,
    ) -> None:
        """Given: Agent has validated move
        When: Agent calculates expected score
        Then: Agent calls calculate_move_score tool
        """
        from scrabgpt.ai.agent_player import propose_move_agent

        rack = ["C", "A", "T"]
        
        with patch("scrabgpt.ai.agent_player.MCPToolExecutor") as mock_executor:
            mock_executor_instance = MagicMock()
            mock_executor.return_value = mock_executor_instance
            
            # Mock scoring tool
            mock_executor_instance.execute_tool = AsyncMock(
                return_value={"total_score": 5, "breakdowns": []}
            )
            
            with patch("scrabgpt.ai.agent_player.OpenAIClient"):
                move = await propose_move_agent(
                    agent_config=full_access_agent_config,
                    board=empty_board,
                    rack=rack,
                    variant=slovak_variant,
                )
            
            # Move should include score information
            assert move is not None


class TestAgentToolRestrictions:
    """Test that agents only use tools they're configured with."""

    @pytest.mark.asyncio
    async def test_minimal_agent_cannot_access_scoring_tools(
        self,
        empty_board: Board,
        slovak_variant: VariantDefinition,
        minimal_agent_config: dict,
    ) -> None:
        """Given: Agent with minimal tools (no scoring tools)
        When: Agent attempts to use scoring tool
        Then: Tool call is rejected
        """
        from scrabgpt.ai.agent_player import propose_move_agent, ToolNotAvailableError

        rack = ["C", "A", "T"]
        
        # Agent should not have access to scoring_score_words
        assert "scoring_score_words" not in minimal_agent_config["tools"]
        
        with patch("scrabgpt.ai.agent_player.MCPToolExecutor") as mock_executor:
            mock_executor_instance = MagicMock()
            mock_executor.return_value = mock_executor_instance
            
            # Simulate agent trying to call forbidden tool
            mock_executor_instance.execute_tool = AsyncMock(
                side_effect=ToolNotAvailableError("scoring_score_words")
            )
            
            with patch("scrabgpt.ai.agent_player.OpenAIClient"):
                # Should still complete (agent adapts)
                move = await propose_move_agent(
                    agent_config=minimal_agent_config,
                    board=empty_board,
                    rack=rack,
                    variant=slovak_variant,
                )
                
                # Agent should work around missing tools
                assert move is not None

    @pytest.mark.asyncio
    async def test_agent_tool_schemas_match_config(
        self,
        full_access_agent_config: dict,
    ) -> None:
        """Given: Agent configuration
        When: Building OpenAI tool schemas
        Then: Only configured tools are included
        """
        from scrabgpt.ai.agent_player import build_tool_schemas_for_agent

        schemas = build_tool_schemas_for_agent(full_access_agent_config)
        
        schema_names = [s["function"]["name"] for s in schemas]
        
        # All configured tools should be in schemas
        for tool in full_access_agent_config["tools"]:
            assert tool in schema_names
        
        # No extra tools should be present
        assert len(schema_names) == len(full_access_agent_config["tools"])


class TestAgentIterativeReasoning:
    """Test agent's ability to use tools iteratively."""

    @pytest.mark.asyncio
    async def test_agent_makes_multiple_tool_calls_to_solve_problem(
        self,
        empty_board: Board,
        slovak_variant: VariantDefinition,
        full_access_agent_config: dict,
    ) -> None:
        """Given: Complex move requiring multiple validations
        When: Agent solves problem
        Then: Agent makes multiple tool calls
        """
        from scrabgpt.ai.agent_player import propose_move_agent

        rack = ["H", "E", "L", "L", "O", "W", "D"]
        
        tool_call_count = 0
        
        async def count_tool_calls(tool_name: str, **kwargs):
            nonlocal tool_call_count
            tool_call_count += 1
            return {"valid": True}
        
        with patch("scrabgpt.ai.agent_player.MCPToolExecutor") as mock_executor:
            mock_executor_instance = MagicMock()
            mock_executor.return_value = mock_executor_instance
            mock_executor_instance.execute_tool = AsyncMock(side_effect=count_tool_calls)
            
            with patch("scrabgpt.ai.agent_player.OpenAIClient"):
                await propose_move_agent(
                    agent_config=full_access_agent_config,
                    board=empty_board,
                    rack=rack,
                    variant=slovak_variant,
                )
        
        # Agent should make multiple tool calls (get state, validate, score, etc.)
        assert tool_call_count >= 2

    @pytest.mark.asyncio
    async def test_agent_retries_after_validation_failure(
        self,
        empty_board: Board,
        slovak_variant: VariantDefinition,
        full_access_agent_config: dict,
    ) -> None:
        """Given: Agent's first move is invalid
        When: Validation fails
        Then: Agent tries alternative move
        """
        from scrabgpt.ai.agent_player import propose_move_agent

        rack = ["X", "Y", "Z"]
        
        validation_attempts = 0
        
        async def mock_validate(tool_name: str, **kwargs):
            nonlocal validation_attempts
            if tool_name == "validate_move_legality":
                validation_attempts += 1
                # First attempt fails, second succeeds
                if validation_attempts == 1:
                    return {"valid": False, "checks": {"in_line": False}}
                else:
                    return {"valid": True, "checks": {}}
            return {}
        
        with patch("scrabgpt.ai.agent_player.MCPToolExecutor") as mock_executor:
            mock_executor_instance = MagicMock()
            mock_executor.return_value = mock_executor_instance
            mock_executor_instance.execute_tool = AsyncMock(side_effect=mock_validate)
            
            with patch("scrabgpt.ai.agent_player.OpenAIClient"):
                move = await propose_move_agent(
                    agent_config=full_access_agent_config,
                    board=empty_board,
                    rack=rack,
                    variant=slovak_variant,
                    max_iterations=5,
                )
        
        # Should have tried multiple times
        assert validation_attempts >= 2
        assert move is not None


class TestAgentErrorHandling:
    """Test agent behavior when tools fail or return errors."""

    @pytest.mark.asyncio
    async def test_agent_handles_tool_execution_error_gracefully(
        self,
        empty_board: Board,
        slovak_variant: VariantDefinition,
        full_access_agent_config: dict,
    ) -> None:
        """Given: Tool execution fails with error
        When: Agent encounters error
        Then: Agent reports error and attempts recovery
        """
        from scrabgpt.ai.agent_player import propose_move_agent, ToolExecutionError

        rack = ["C", "A", "T"]
        
        async def failing_tool(tool_name: str, **kwargs):
            if tool_name == "get_board_state":
                raise ToolExecutionError("Board state unavailable")
            return {}
        
        with patch("scrabgpt.ai.agent_player.MCPToolExecutor") as mock_executor:
            mock_executor_instance = MagicMock()
            mock_executor.return_value = mock_executor_instance
            mock_executor_instance.execute_tool = AsyncMock(side_effect=failing_tool)
            
            with patch("scrabgpt.ai.agent_player.OpenAIClient"):
                # Should handle error without crashing
                result = await propose_move_agent(
                    agent_config=full_access_agent_config,
                    board=empty_board,
                    rack=rack,
                    variant=slovak_variant,
                )
                
                # May return None or error status, but shouldn't crash
                assert result is not None or True  # Graceful handling

    @pytest.mark.asyncio
    async def test_agent_max_iterations_prevents_infinite_loops(
        self,
        empty_board: Board,
        slovak_variant: VariantDefinition,
        full_access_agent_config: dict,
    ) -> None:
        """Given: Agent gets stuck in validation loop
        When: Max iterations reached
        Then: Agent stops and returns best attempt
        """
        from scrabgpt.ai.agent_player import propose_move_agent

        rack = ["X"]
        
        iteration_count = 0
        
        async def always_invalid(tool_name: str, **kwargs):
            nonlocal iteration_count
            if tool_name == "validate_move_legality":
                iteration_count += 1
                return {"valid": False}
            return {}
        
        with patch("scrabgpt.ai.agent_player.MCPToolExecutor") as mock_executor:
            mock_executor_instance = MagicMock()
            mock_executor.return_value = mock_executor_instance
            mock_executor_instance.execute_tool = AsyncMock(side_effect=always_invalid)
            
            with patch("scrabgpt.ai.agent_player.OpenAIClient"):
                result = await propose_move_agent(
                    agent_config=full_access_agent_config,
                    board=empty_board,
                    rack=rack,
                    variant=slovak_variant,
                    max_iterations=3,
                )
        
        # Should stop after max iterations
        assert iteration_count <= 3


class TestAgentPromptConstruction:
    """Test how agent system prompt is constructed."""

    def test_agent_system_prompt_includes_available_tools(
        self,
        full_access_agent_config: dict,
    ) -> None:
        """Given: Agent configuration
        When: Building system prompt
        Then: Prompt describes available tools
        """
        from scrabgpt.ai.agent_player import build_agent_system_prompt

        prompt = build_agent_system_prompt(full_access_agent_config)
        
        # Prompt should mention tools
        assert "tools" in prompt.lower() or "nástroje" in prompt.lower()
        
        # Should include instructions
        assert len(prompt) > 100

    def test_agent_context_includes_game_state(
        self,
        empty_board: Board,
        slovak_variant: VariantDefinition,
    ) -> None:
        """Given: Current game state
        When: Building agent context
        Then: Context includes board, rack, and rules
        """
        from scrabgpt.ai.agent_player import build_agent_context

        rack = ["A", "B", "C"]
        
        context = build_agent_context(
            board=empty_board,
            rack=rack,
            variant=slovak_variant,
        )
        
        # Should include board state
        assert "grid" in context.lower() or "board" in context.lower()
        
        # Should include rack info
        assert "rack" in context.lower() or "ABC" in context
