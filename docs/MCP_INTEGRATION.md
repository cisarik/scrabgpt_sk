# MCP Integration for ScrabGPT

This document explains the Model Context Protocol (MCP) integration in ScrabGPT using the `mcp-use` framework.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Components](#components)
4. [Usage](#usage)
5. [Development](#development)
6. [Testing](#testing)
7. [Troubleshooting](#troubleshooting)

## Overview

ScrabGPT integrates with the [Model Context Protocol (MCP)](https://modelcontextprotocol.io) to provide a standardized way for AI agents to access Scrabble game logic. This allows:

- **AI agents** to validate moves, calculate scores, and check game rules
- **Multiple LLM providers** to use the same tool interface
- **External tools** to integrate with ScrabGPT's game logic
- **Developer-friendly** JSON-based tool definitions

### What is MCP?

MCP is an open protocol that standardizes how AI systems access external resources and tools. Think of it as "USB for AI" - it provides a universal interface for connecting AI models to data and functionality.

### Why mcp-use?

[mcp-use](https://mcp-use.com) is a Python library that makes it easy to:
- Connect LLMs (via LangChain) to MCP servers
- Build agents that can use multiple MCP servers
- Handle async operations and error handling
- Support various transports (stdio, HTTP, SSE)

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     AI Application                       │
│  (LangChain Agent + OpenAI/Anthropic/etc.)              │
└────────────────────┬─────────────────────────────────────┘
                     │
                     │ Natural Language Queries
                     ▼
┌──────────────────────────────────────────────────────────┐
│                    MCPAgent (mcp-use)                    │
│  - Converts queries to tool calls                        │
│  - Manages agent loop (reasoning + tool execution)       │
│  - Aggregates results                                    │
└────────────────────┬─────────────────────────────────────┘
                     │
                     │ MCP Protocol (JSON-RPC)
                     ▼
┌──────────────────────────────────────────────────────────┐
│                MCPClient (mcp-use)                       │
│  - Discovers available tools                             │
│  - Routes tool calls to correct server                   │
│  - Handles multiple server connections                   │
└────────────────────┬─────────────────────────────────────┘
                     │
                     │ stdio/HTTP/SSE
                     ▼
┌──────────────────────────────────────────────────────────┐
│           ScrabGPT MCP Server (mcp_server.py)           │
│  - Exposes 11 Scrabble game logic tools                 │
│  - Tool discovery (list_tools)                           │
│  - Tool execution (call_tool)                            │
│  - JSON schema validation                                │
└────────────────────┬─────────────────────────────────────┘
                     │
                     │ Python function calls
                     ▼
┌──────────────────────────────────────────────────────────┐
│               MCP Tools (mcp_tools.py)                   │
│  - Stateless tool functions                              │
│  - JSON input/output                                     │
│  - Error handling                                        │
└────────────────────┬─────────────────────────────────────┘
                     │
                     │ Domain logic calls
                     ▼
┌──────────────────────────────────────────────────────────┐
│             Core Game Logic (core/)                      │
│  - Board, Rules, Scoring, Tiles                          │
│  - Pure Python, no external dependencies                 │
└──────────────────────────────────────────────────────────┘
```

## Components

### 1. MCP Server (`scrabgpt/ai/mcp_server.py`)

The MCP server exposes ScrabGPT's game logic via the MCP protocol.

**Key Features:**
- **11 tools** exposed (rules, scoring, state)
- **JSON Schema validation** for all tool inputs
- **Async support** for concurrent tool calls
- **Error handling** with structured error responses
- **stdio transport** for local integration

**Running the server:**
```bash
# Start server (blocks on stdio)
poetry run python -m scrabgpt.ai.mcp_server
```

### 2. MCP Tools (`scrabgpt/ai/mcp_tools.py`)

Stateless functions that implement game logic tools. Each tool:
- Takes JSON-serializable arguments
- Returns JSON-serializable results
- Has comprehensive docstrings
- Handles errors gracefully

**Tool Categories:**

#### Rule Validation Tools
- `rules_first_move_must_cover_center` - Check if first move covers (7,7)
- `rules_placements_in_line` - Check if placements form a line
- `rules_connected_to_existing` - Check connection to board
- `rules_no_gaps_in_line` - Check for gaps in main line
- `rules_extract_all_words` - Extract all words formed

#### Scoring Tools
- `scoring_score_words` - Calculate score with premium breakdown

#### State/Info Tools
- `get_board_state` - Get board as serialized grid
- `get_rack_letters` - Get available rack letters
- `get_tile_values` - Get point values for variant

#### High-Level Composite Tools
- `validate_move_legality` - Complete move validation (all rules)
- `calculate_move_score` - Complete score calculation (extract + score)

### 3. Configuration (`scrabble_mcp.json`)

MCP client configuration for connecting to ScrabGPT server:

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

### 4. Examples (`examples/`)

- `mcp_agent_demo.py` - Comprehensive demos of MCP usage
- `README.md` - Usage guide and API reference

### 5. Tests (`tests/test_mcp_server.py`)

- **Unit tests** - Server initialization, schema validation
- **Integration tests** - Tool calling, error handling
- **Stress tests** - All tools with various inputs

## Usage

### Basic Example: Using MCP Agent

```python
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient

load_dotenv()

async def main():
    # Load configuration
    with open("scrabble_mcp.json") as f:
        config = json.load(f)
    
    # Create MCP client and connect to server
    client = MCPClient.from_dict(config)
    
    # Create LLM
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    # Create agent with MCP tools
    agent = MCPAgent(llm=llm, client=client, max_steps=20)
    
    # Query the agent
    result = await agent.run(
        "What are the tile point values in the Slovak variant?"
    )
    print(result)

asyncio.run(main())
```

### Advanced Example: Move Validation

```python
async def validate_move():
    # Setup (same as above)
    client = MCPClient.from_dict(config)
    llm = ChatOpenAI(model="gpt-4o")
    agent = MCPAgent(llm=llm, client=client)
    
    # Complex query requiring multiple tool calls
    query = """
    I want to play "CATS" horizontally at row 7, starting at column 6.
    The placements are:
    - (7, 6): C
    - (7, 7): A  (center square)
    - (7, 8): T
    - (7, 9): S
    
    Is this a legal first move? If yes, what's the score?
    Use Slovak tile values.
    """
    
    result = await agent.run(query)
    print(result)
```

### Direct Tool Calls (Without Agent)

```python
from scrabgpt.ai import mcp_tools

# Call tool directly
result = mcp_tools.tool_validate_move_legality(
    board_grid=["." * 15] * 15,  # Empty board
    placements=[
        {"row": 7, "col": 6, "letter": "C"},
        {"row": 7, "col": 7, "letter": "A"},
        {"row": 7, "col": 8, "letter": "T"},
    ],
    is_first_move=True,
)

print(result)
# {
#   "valid": True,
#   "checks": {"in_line": True, "covers_center": True, ...},
#   "reason": "Move is legal"
# }
```

## Development

### Adding New Tools

1. **Add tool function** to `scrabgpt/ai/mcp_tools.py`:

```python
def tool_my_new_feature(arg1: str, arg2: int) -> dict[str, Any]:
    """My new tool description.
    
    Args:
        arg1: Description of arg1
        arg2: Description of arg2
    
    Returns:
        {result: Any, success: bool}
    """
    try:
        # Implementation
        return {"result": "something", "success": True}
    except Exception as e:
        log.exception("Error in tool_my_new_feature")
        return {"result": None, "success": False, "error": str(e)}

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
            "arg1": {
                "type": "string",
                "description": "Description of arg1",
            },
            "arg2": {
                "type": "integer",
                "description": "Description of arg2",
                "minimum": 0,
            },
        },
        "required": ["arg1", "arg2"],
    },
}
```

3. **Add tests** to `tests/test_mcp_server.py`:

```python
@pytest.mark.asyncio
async def test_my_new_feature():
    """Test my new feature tool."""
    result = await mcp_server.call_tool(
        name="my_new_feature",
        arguments={"arg1": "test", "arg2": 42},
    )
    
    data = json.loads(result[0].text)
    assert data["success"] is True
    assert "result" in data
```

### Tool Design Guidelines

1. **Stateless:** Tools should not maintain state between calls
2. **JSON-serializable:** All inputs/outputs must be JSON-serializable
3. **Error handling:** Always catch exceptions and return structured errors
4. **Validation:** Validate inputs and provide clear error messages
5. **Documentation:** Comprehensive docstrings with examples
6. **Testing:** Unit tests + integration tests

## Testing

### Running Tests

```bash
# Run all offline tests
poetry run pytest tests/test_mcp_server.py -v

# Run with internet tests (requires OpenAI API key)
poetry run pytest tests/test_mcp_server.py -v -m internet

# Run stress tests
poetry run pytest tests/test_mcp_server.py -v -m stress
```

### Test Categories

- **Unit tests:** Server initialization, schema validation, tool registration
- **Integration tests:** Tool calling via MCP protocol, error handling
- **Stress tests:** All tools with various inputs, performance testing

### Example Test

```python
@pytest.mark.asyncio
async def test_call_tool_get_tile_values():
    """Test calling get_tile_values tool."""
    result = await mcp_server.call_tool(
        name="get_tile_values",
        arguments={"variant": "slovak"},
    )
    
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert "values" in data
    assert "variant" in data
    assert isinstance(data["values"], dict)
```

## Troubleshooting

### Common Issues

#### 1. MCP Server Won't Start

**Symptom:** `ModuleNotFoundError: No module named 'mcp'`

**Solution:**
```bash
# Ensure mcp-use is installed
poetry install

# Run with poetry environment
poetry run python -m scrabgpt.ai.mcp_server
```

#### 2. Tool Not Found Error

**Symptom:** `{"error": "Tool not found: tool_name"}`

**Causes:**
- Tool not registered in `ALL_TOOLS` dict
- Tool name mismatch between schema and function
- Typo in tool name

**Solution:**
Check that tool is registered:
```python
from scrabgpt.ai import mcp_tools
print(mcp_tools.get_all_tool_names())
```

#### 3. Invalid Arguments Error

**Symptom:** `TypeError: tool_xxx() got an unexpected keyword argument 'yyy'`

**Causes:**
- Schema doesn't match function signature
- Extra arguments being passed
- Missing required arguments

**Solution:**
Compare schema in `TOOL_SCHEMAS` with function signature in `mcp_tools.py`.

#### 4. OpenAI API Key Not Found

**Symptom:** `Error: OpenAI API key not found`

**Solution:**
```bash
# Check .env file
cat .env | grep OPENAI_API_KEY

# Or set directly
export OPENAI_API_KEY='sk-...'

# Verify loading
poetry run python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('Key:', os.getenv('OPENAI_API_KEY')[:10] + '...')"
```

#### 5. JSON Serialization Error

**Symptom:** `TypeError: Object of type X is not JSON serializable`

**Causes:**
- Tool returning non-JSON types (e.g., Board objects)
- Datetime objects not converted to strings
- Custom objects in response

**Solution:**
Convert all objects to JSON-serializable types:
```python
# Bad
return {"board": board_obj}

# Good
return {"board": board_obj.to_dict()}
```

### Debugging Tips

1. **Enable verbose logging:**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Test tool directly:**
   ```python
   from scrabgpt.ai import mcp_tools
   result = mcp_tools.tool_get_tile_values(variant="slovak")
   print(result)
   ```

3. **Check server status:**
   ```bash
   poetry run python -c "from scrabgpt.ai import mcp_server; print(f'Server: {mcp_server.server.name}, Tools: {len(mcp_server.TOOL_SCHEMAS)}')"
   ```

4. **Verify configuration:**
   ```bash
   cat scrabble_mcp.json | jq .
   ```

## Resources

- **mcp-use Documentation:** https://docs.mcp-use.com
- **MCP Specification:** https://modelcontextprotocol.io
- **LangChain Docs:** https://python.langchain.com
- **ScrabGPT Agent Tutorial:** See `AGENT_PATTERN_TUTORIAL.md`
- **Examples:** See `examples/mcp_agent_demo.py`

## Performance

### Benchmarks

Measured on development machine (Python 3.13, localhost):

| Operation | Time | Notes |
|-----------|------|-------|
| Server startup | ~200ms | One-time cost |
| List tools | ~5ms | Cached after first call |
| Call tool (simple) | ~10-50ms | e.g., get_tile_values |
| Call tool (complex) | ~50-200ms | e.g., validate_move_legality |
| Agent query (3 tools) | ~2-5s | Includes LLM latency |

### Optimization Tips

1. **Batch tool calls** when possible
2. **Cache results** for expensive operations
3. **Use async operations** for concurrent tool calls
4. **Minimize LLM calls** by using high-level composite tools

## Future Enhancements

- [ ] Add HTTP transport support
- [ ] Implement tool caching/memoization
- [ ] Add telemetry and monitoring
- [ ] Support streaming responses
- [ ] Add authentication/authorization
- [ ] Multi-language support
- [ ] Tool versioning
- [ ] Performance profiling

## License

Same as ScrabGPT main project.
