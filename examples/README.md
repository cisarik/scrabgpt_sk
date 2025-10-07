# ScrabGPT MCP Examples

This directory contains example scripts demonstrating how to use ScrabGPT's MCP (Model Context Protocol) server with mcp-use and LangChain.

## Examples

### 1. `mcp_agent_demo.py`

Comprehensive demonstration of the ScrabGPT MCP server including:

- **Demo 1:** Basic Scrabble rules query (tile values)
- **Demo 2:** Move validation (checking if a move is legal)
- **Demo 3:** Score calculation (calculating points for a move)
- **Demo 4:** Direct tool calls (lower-level API without agent)

**Usage:**
```bash
# Ensure .env has OPENAI_API_KEY set
poetry run python examples/mcp_agent_demo.py
```

**What it demonstrates:**
- Connecting to MCP server via configuration file
- Creating AI agents with access to Scrabble game logic
- Natural language queries that use MCP tools
- Direct tool invocation without agent wrapper

### 2. More examples coming soon!

- Game playing agent (proposes optimal moves)
- Multi-agent gameplay (two AI agents playing against each other)
- Custom tool composition (building complex strategies)

## Prerequisites

1. **Environment Setup:**
   ```bash
   cp .env.example .env
   # Add your OPENAI_API_KEY
   ```

2. **Dependencies:**
   ```bash
   poetry install  # Already includes mcp-use, langchain-openai
   ```

3. **MCP Server Configuration:**
   
   The `scrabble_mcp.json` file in the project root defines the server:
   ```json
   {
     "mcpServers": {
       "scrabble": {
         "command": "poetry",
         "args": ["run", "python", "-m", "scrabgpt.ai.mcp_server"],
         "env": {},
         "description": "ScrabGPT MCP Server"
       }
     }
   }
   ```

## Available MCP Tools

The ScrabGPT MCP server exposes these tools:

### Rule Validation
- `rules_first_move_must_cover_center` - Check if first move covers center
- `rules_placements_in_line` - Check if placements form a line
- `rules_connected_to_existing` - Check if move connects to board
- `rules_no_gaps_in_line` - Check for gaps in line
- `rules_extract_all_words` - Extract all words formed by move

### Scoring
- `scoring_score_words` - Calculate score with premium breakdown

### Board State
- `get_board_state` - Get current board as serialized grid
- `get_rack_letters` - Get available rack letters
- `get_tile_values` - Get point values for variant

### High-Level
- `validate_move_legality` - Complete move validation (all rules)
- `calculate_move_score` - Complete score calculation (extract + score)

## Architecture

```
┌─────────────────┐
│   AI Agent      │  (LangChain + OpenAI)
│  (Natural Lang) │
└────────┬────────┘
         │
         │ mcp-use
         ▼
┌─────────────────┐
│   MCP Client    │  (mcp_use.MCPClient)
└────────┬────────┘
         │
         │ stdio/HTTP
         ▼
┌─────────────────┐
│   MCP Server    │  (scrabgpt.ai.mcp_server)
│  (Tool Router)  │
└────────┬────────┘
         │
         │ Function calls
         ▼
┌─────────────────┐
│   MCP Tools     │  (scrabgpt.ai.mcp_tools)
│  (Game Logic)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Core Modules   │  (board, rules, scoring)
└─────────────────┘
```

## Development

### Running the MCP Server Directly

```bash
# Start server (stdio mode)
poetry run python -m scrabgpt.ai.mcp_server

# The server will wait for MCP protocol messages on stdin
# and write responses to stdout
```

### Testing Individual Tools

```python
from scrabgpt.ai import mcp_tools

# Call tool directly (synchronous)
result = mcp_tools.tool_get_tile_values(variant="slovak")
print(result)
# {'values': {'A': 1, 'B': 2, ...}, 'variant': 'slovak'}

# Validate move legality
result = mcp_tools.tool_validate_move_legality(
    board_grid=["." * 15] * 15,
    placements=[
        {"row": 7, "col": 6, "letter": "C"},
        {"row": 7, "col": 7, "letter": "A"},
        {"row": 7, "col": 8, "letter": "T"},
    ],
    is_first_move=True,
)
print(result)
# {'valid': True, 'checks': {...}, 'reason': 'Move is legal'}
```

### Adding New Tools

1. **Add tool function** to `scrabgpt/ai/mcp_tools.py`:
   ```python
   def tool_my_new_feature(arg1: str) -> dict[str, Any]:
       """My new tool description."""
       return {"result": "something"}
   
   # Register in ALL_TOOLS dict
   ALL_TOOLS["my_new_feature"] = tool_my_new_feature
   ```

2. **Add tool schema** to `scrabgpt/ai/mcp_server.py`:
   ```python
   TOOL_SCHEMAS["my_new_feature"] = {
       "name": "my_new_feature",
       "description": "My new tool description",
       "inputSchema": {
           "type": "object",
           "properties": {
               "arg1": {"type": "string", "description": "..."}
           },
           "required": ["arg1"],
       },
   }
   ```

3. **Test it:**
   ```bash
   poetry run python -c "
   from scrabgpt.ai import mcp_tools
   result = mcp_tools.tool_my_new_feature('test')
   print(result)
   "
   ```

## Troubleshooting

### MCP Server Won't Start

```bash
# Check if server module loads
poetry run python -c "from scrabgpt.ai import mcp_server; print('OK')"

# Check if mcp package is installed
poetry run python -c "import mcp; print(mcp.__version__)"
```

### Agent Can't Find Tools

Ensure your configuration file path is correct:
```python
config_path = Path(__file__).parent.parent / "scrabble_mcp.json"
assert config_path.exists(), f"Config not found: {config_path}"
```

### OpenAI API Key Not Found

```bash
# Check .env file
cat .env | grep OPENAI_API_KEY

# Or set directly
export OPENAI_API_KEY='sk-...'
```

## Resources

- **mcp-use Documentation:** https://docs.mcp-use.com
- **MCP Specification:** https://modelcontextprotocol.io
- **LangChain Docs:** https://python.langchain.com
- **ScrabGPT Documentation:** See parent directory's `AGENTS.md`, `AGENT_PATTERN_TUTORIAL.md`

## License

Same as ScrabGPT main project.
