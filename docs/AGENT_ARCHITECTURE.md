# AI Agent Architecture with MCP Tools

## Overview

This document describes the AI agent architecture implemented using Model Context Protocol (MCP) tools. The system allows AI opponents to access game state and validation tools, enabling more sophisticated gameplay through iterative reasoning.

## Architecture Components

### 1. MCP Tools (`scrabgpt/ai/mcp_tools.py`)

Stateless tool functions exposed to AI agents. Each tool is JSON-serializable and categorized:

#### Rule Validation Tools
- `tool_rules_first_move_must_cover_center` - Validates center coverage
- `tool_rules_placements_in_line` - Checks line formation (ACROSS/DOWN)
- `tool_rules_connected_to_existing` - Verifies connection to board
- `tool_rules_no_gaps_in_line` - Detects gaps in placement
- `tool_rules_extract_all_words` - Extracts main + cross words

#### Scoring Tools
- `tool_scoring_score_words` - Calculates score with premium breakdown

#### Information Tools
- `tool_get_board_state` - Returns serialized board grid
- `tool_get_rack_letters` - Returns available letters
- `tool_get_premium_squares` - Returns unused premiums
- `tool_get_tile_values` - Returns point values per letter

#### Dictionary Tools
- `tool_validate_word_slovak` - 3-tier Slovak validation (stub)
- `tool_validate_word_english` - 3-tier English validation (stub)

#### Composite Tools
- `tool_validate_move_legality` - Complete rule validation
- `tool_calculate_move_score` - Word extraction + scoring

### 2. Agent Configuration (`scrabgpt/ai/agent_config.py`)

Manages `.agent` configuration files that define agents with specific tool access:

```json
{
  "name": "Agent Name",
  "description": "Description",
  "model": "gpt-4o",
  "tools": ["tool1", "tool2", ...]
}
```

**Key Functions:**
- `load_agent_config(path)` - Loads and validates .agent file
- `discover_agents(dir)` - Finds all valid .agent files
- `validate_agent_tools(config)` - Ensures tools exist
- `build_tool_schemas(tools)` - Generates OpenAI function schemas

### 3. Agent Player (`scrabgpt/ai/agent_player.py`)

**STATUS: STUB IMPLEMENTATION**

Implements AI player using MCP tools via OpenAI function calling.

**Components:**
- `MCPToolExecutor` - Enforces tool access control
- `propose_move_agent()` - Main entry point (stub)
- `build_agent_system_prompt()` - Generates system prompt
- `build_agent_context()` - Serializes game state

**TODO: Full Implementation Requires:**
1. OpenAI function calling loop
2. Tool call handling and execution
3. State management across iterations
4. Validation and retry logic
5. Error handling and recovery

### 4. Opponent Mode (`scrabgpt/core/opponent_mode.py`)

Enum defining AI opponent modes:

```python
class OpponentMode(Enum):
    AGENT = "agent"           # MCP agent with tools
    BEST_MODEL = "best_model" # Auto-updated best model
    SINGLE = "single"         # Simple single model
    OPENROUTER = "openrouter" # Multi-model competition
    OFFLINE = "offline"       # Local AI (future)
```

Each mode has Slovak display names and descriptions for UI.

## Predefined Agents

### Full Access (`agents/full_access.agent`)
- **Model:** gpt-4o
- **Tools:** All 14 tools
- **Use Case:** Maximum capability, best performance

### Rule Master (`agents/rule_master.agent`)
- **Model:** gpt-4o-mini
- **Tools:** All rules + info, no scoring
- **Use Case:** Must estimate scores mentally

### Minimal (`agents/minimal.agent`)
- **Model:** gpt-4o-mini
- **Tools:** Basic info + validation only
- **Use Case:** Most challenging, tests reasoning

### Scorer (`agents/scorer.agent`)
- **Model:** gpt-4o
- **Tools:** Scoring focus, limited rules
- **Use Case:** Tests if scoring helps vs rules

## Test-Driven Development

### Test Files Created

1. **`tests/test_mcp_tools.py`** (228 tests defined)
   - Tests each tool function independently
   - Validates JSON serialization
   - Checks error handling
   - BDD-style: Given/When/Then

2. **`tests/test_agent_config.py`** (80 tests defined)
   - Tests .agent file parsing
   - Validates schema enforcement
   - Tests agent discovery
   - Tests tool registry

3. **`tests/test_agent_player.py`** (90 tests defined)
   - Tests agent move generation
   - Tests tool usage patterns
   - Tests iterative reasoning
   - Tests error handling

### Running Tests

```bash
# Collect all agent tests
poetry run pytest tests/test_mcp_tools.py tests/test_agent_config.py tests/test_agent_player.py --collect-only

# Run specific test file
poetry run pytest tests/test_mcp_tools.py -v

# Run specific test
poetry run pytest tests/test_mcp_tools.py::TestRuleTools::test_rules_first_move_must_cover_center_validates_correctly -v
```

**Note:** Most tests will fail until full implementation is complete. This is expected in TDD.

## Environment Configuration

Added to `.env.example`:

```bash
# Opponent mode configuration
OPENAI_PLAYER_MODEL='gpt-4o-mini'       # Default model for single mode
OPENAI_BEST_MODEL_AUTO_UPDATE='true'    # Auto-fetch best model
DEFAULT_OPPONENT_MODE='single'          # Default opponent mode
DEFAULT_AGENT_NAME='Plný Prístup'       # Default agent selection
```

## Next Steps

### Phase 1: Core MCP Integration (High Priority)

1. **Install mcp-use library**
   ```bash
   poetry add mcp-use
   ```

2. **Implement OpenAI function calling loop** in `agent_player.py`:
   - Call OpenAI with tool schemas
   - Parse `tool_calls` from response
   - Execute tools via `MCPToolExecutor`
   - Feed results back to OpenAI
   - Repeat until final answer
   - Parse and return move

3. **Implement tool schema generation**:
   - Extract parameter types from function signatures
   - Generate proper OpenAI function schemas
   - Include descriptions and required fields

4. **Add proper error handling**:
   - Retry on transient failures
   - Max iteration limits
   - Graceful degradation

### Phase 2: Dictionary Validation (Medium Priority)

5. **Implement Slovak 3-tier validation**:
   - Tier 1: In-memory dictionary (fast lookup)
   - Tier 2: HTTP call to JULS API (when available)
   - Tier 3: AI judge fallback

6. **Implement English 3-tier validation**:
   - Tier 1: Load TWL/SOWPODS dictionary
   - Tier 2: HTTP call to Wordnik/Merriam-Webster API
   - Tier 3: AI judge fallback

7. **Add dictionary loading on startup**:
   - Load word lists into memory
   - Cache HTTP responses
   - Track validation tier usage

### Phase 3: UI Integration (Medium Priority)

8. **Update Settings Window**:
   - Add opponent mode radio buttons
   - Add agent dropdown (populated from discovered agents)
   - Add "Download Best Model Info" button
   - Show agent description and tool list
   - Save/load opponent mode preference

9. **Update Main Window**:
   - Display current opponent mode in status
   - Show agent name when in agent mode
   - Track tool usage statistics
   - Display tool call logs in debug mode

10. **Wire up opponent mode logic** in `app.py`:
    ```python
    if opponent_mode == OpponentMode.AGENT:
        move = await propose_move_agent(agent_config, board, rack, variant)
    elif opponent_mode == OpponentMode.BEST_MODEL:
        move = await propose_move_best_model(board, rack, variant)
    elif opponent_mode == OpponentMode.SINGLE:
        move = ai_propose_move(client, state, variant)  # Existing
    elif opponent_mode == OpponentMode.OPENROUTER:
        move, results = await propose_move_multi_model(...)  # Existing
    ```

### Phase 4: Experimentation & Optimization (Low Priority)

11. **Create experiment tracking**:
    - Log agent performance metrics
    - Track tool usage frequency
    - Measure move generation time
    - Compare win rates

12. **Add agent comparison mode**:
    - Run multiple agents on same position
    - Compare proposed moves
    - Analyze which tools were used

13. **Optimize tool subsets**:
    - Identify minimum viable tool set
    - Find tool combinations that maximize performance
    - Balance tool access vs API cost

## Known Limitations & TODOs

### Current Stub Implementations

- ❌ `propose_move_agent()` - Not functional (raises NotImplementedError)
- ❌ `tool_validate_word_slovak()` - Returns stub (always valid)
- ❌ `tool_validate_word_english()` - Not implemented
- ❌ `get_tool_schema()` - Returns basic schema without parameters
- ❌ OpenAI function calling loop - Not implemented

### Missing Features

- No "Best Model" auto-update mechanism
- No offline AI integration
- No English dictionary loaded
- No Slovak in-memory dictionary loaded
- No JULS API integration
- No Wordnik/Merriam-Webster API integration
- No UI for opponent mode selection
- No agent statistics tracking
- No tool usage analytics

## Learning Resources

### MCP (Model Context Protocol)

- **mcp-use GitHub:** https://github.com/mcp-use/mcp-use
- **OpenAI Function Calling:** https://platform.openai.com/docs/guides/function-calling
- **MCP Specification:** https://github.com/modelcontextprotocol/specification

### Dictionary APIs

- **JULS (Slovak):** http://juls.savba.sk/ (investigate API availability)
- **Wordnik (English):** https://developer.wordnik.com/
- **Merriam-Webster (English):** https://dictionaryapi.com/

### Agent Patterns

- **ReAct Pattern:** Reasoning + Acting with tools
- **Chain-of-Thought:** Iterative reasoning through problems
- **Tool-Use Agents:** Agents that call external functions

## File Structure

```
scrabgpt_sk/
├── agents/                          # Agent configurations
│   ├── full_access.agent
│   ├── rule_master.agent
│   ├── minimal.agent
│   ├── scorer.agent
│   └── README.md
├── scrabgpt/
│   ├── ai/
│   │   ├── mcp_tools.py            # MCP tool wrappers
│   │   ├── agent_config.py         # Agent loading/validation
│   │   ├── agent_player.py         # Agent player (stub)
│   │   ├── player.py               # Single model player (existing)
│   │   └── multi_model.py          # Multi-model (existing)
│   └── core/
│       └── opponent_mode.py        # Opponent mode enum
├── tests/
│   ├── test_mcp_tools.py           # MCP tool tests
│   ├── test_agent_config.py        # Agent config tests
│   └── test_agent_player.py        # Agent player tests
├── docs/
│   └── AGENT_ARCHITECTURE.md       # This document
└── .env.example                    # Environment variables

```

## Contributing

When adding new tools:

1. Add tool function to `mcp_tools.py`
2. Register in `ALL_TOOLS` dict
3. Add test in `test_mcp_tools.py`
4. Update agent configurations as needed
5. Document in this file

When creating new agents:

1. Create `.agent` file in `agents/`
2. Follow JSON schema
3. Test agent loads correctly
4. Document purpose and use case
5. Add to predefined agents list

## Questions & Decisions

### Why separate tool functions from core logic?

MCP tools are wrappers that ensure JSON serialization and provide consistent error handling. Core logic stays pure for testing.

### Why not expose entire Board object to agent?

Serialization keeps tools stateless and testable. Also prevents agent from modifying board directly.

### Why multiple agents instead of one configurable agent?

Experimentation! We want to discover which tool combinations work best. Named agents make comparison easier.

### Why TDD for this feature?

MCP integration has many edge cases (tool errors, invalid schemas, retry logic). Tests define expected behavior before implementation complexity.

### Should we use function calling or direct MCP?

Start with OpenAI function calling (simpler). Consider full MCP protocol later if needed for non-OpenAI models.

## Status Summary

✅ **Complete:**
- MCP tool wrappers (14 tools)
- Agent configuration system
- Agent discovery and loading
- Opponent mode enum
- TDD test suite (3 files, ~400 tests)
- Example agent configs (4 agents)
- Environment variable setup
- Documentation

⏳ **Stub/Partial:**
- Agent player (stub raises NotImplementedError)
- Tool schema generation (basic only)
- Dictionary validation (stub returns always valid)

❌ **Not Started:**
- OpenAI function calling loop
- MCP tool execution integration
- Dictionary loading (Slovak/English)
- HTTP API integrations (JULS, Wordnik)
- UI opponent mode selection
- Best model auto-update
- Agent statistics tracking

## Estimated Effort

- **Phase 1 (Core MCP):** 8-16 hours
- **Phase 2 (Dictionaries):** 6-12 hours
- **Phase 3 (UI):** 4-8 hours
- **Phase 4 (Optimization):** Ongoing

**Total:** ~20-40 hours for full implementation

## Contact & Questions

For questions about this architecture, see:
- `AGENTS.md` - General project guidelines
- `PRD.md` - Product requirements
- `tests/iq_tests/README.md` - IQ test system
