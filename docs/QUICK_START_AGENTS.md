# Quick Start: AI Agent System

## ✅ What's Ready Now

Your AI agent system foundation is **complete and tested**. Here's what you can do immediately:

### 1. List All Available Agents

```bash
poetry run python -c "from scrabgpt.ai.agent_config import discover_agents, get_default_agents_dir; import json; agents = discover_agents(get_default_agents_dir()); print(json.dumps([{'name': a['name'], 'model': a['model'], 'tools': len(a['tools'])} for a in agents], indent=2))"
```

**Output:**
```json
[
  {
    "name": "Minimálny Agent",
    "model": "gpt-4o-mini",
    "tools": 3
  },
  {
    "name": "Plný Prístup",
    "model": "gpt-4o",
    "tools": 13
  },
  {
    "name": "Bodovač",
    "model": "gpt-4o",
    "tools": 9
  },
  {
    "name": "Majster Pravidiel",
    "model": "gpt-4o-mini",
    "tools": 11
  }
]
```

### 2. List All Available MCP Tools

```bash
poetry run python -c "from scrabgpt.ai.mcp_tools import get_all_tool_names; import json; print(json.dumps(get_all_tool_names(), indent=2))"
```

**Output:** 14 tools including rules, scoring, state, and dictionary validation.

### 3. Test a Tool Function

```bash
poetry run python -c "from scrabgpt.ai.mcp_tools import tool_get_rack_letters; print(tool_get_rack_letters(['H', 'E', 'L', 'L', 'O', 'W', 'D']))"
```

**Output:**
```python
{'rack': 'HELLOWD', 'count': 7, 'letters': ['H', 'E', 'L', 'L', 'O', 'W', 'D']}
```

### 4. Run Test Suite

```bash
# Collect all tests (50 tests)
poetry run pytest tests/test_mcp_tools.py tests/test_agent_config.py tests/test_agent_player.py --collect-only

# Run just agent config tests (should pass)
poetry run pytest tests/test_agent_config.py::TestAgentConfigDefaults::test_default_agents_directory_exists -v
```

### 5. Verify Opponent Mode Enum

```bash
poetry run python -c "from scrabgpt.core.opponent_mode import OpponentMode; print([mode.value for mode in OpponentMode])"
```

**Output:**
```python
['agent', 'best_model', 'single', 'openrouter', 'offline']
```

---

## 🚧 What's Not Working Yet

### Agent Player (Main Implementation Needed)

```python
from scrabgpt.ai.agent_player import propose_move_agent

# This will raise NotImplementedError
move = await propose_move_agent(agent_config, board, rack, variant)
```

**Error:** `NotImplementedError: Agent player requires full MCP integration...`

**Why:** The OpenAI function calling loop is not implemented yet.

### Dictionary Validation (Stubs Only)

```python
from scrabgpt.ai.mcp_tools import tool_validate_word_slovak

result = tool_validate_word_slovak("XYZQQ")
```

**Output:** `{'valid': True, 'tier': 0, 'reason': 'Validation not implemented - stub only'}`

**Why:** Always returns valid - 3-tier validation not implemented.

---

## 🎯 Your Next Task: Make Agent Mode Work

### Step 1: Understand OpenAI Function Calling

Read: https://platform.openai.com/docs/guides/function-calling

Key concept: AI can call functions you provide, then use results to generate final answer.

### Step 2: Implement the Loop in `agent_player.py`

Replace this stub:

```python
async def propose_move_agent(...):
    raise NotImplementedError(...)
```

With this pattern:

```python
async def propose_move_agent(
    agent_config: dict[str, Any],
    board: Board,
    rack: list[str],
    variant: VariantDefinition,
    max_iterations: int = 10,
) -> dict[str, Any]:
    """Propose move using AI agent with MCP tools."""
    
    # 1. Setup
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    executor = MCPToolExecutor(agent_config["tools"])
    tool_schemas = build_tool_schemas_for_agent(agent_config)
    
    # 2. Build initial messages
    system_prompt = build_agent_system_prompt(agent_config)
    context = build_agent_context(board, rack, variant)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context}
    ]
    
    # 3. Iterative function calling loop
    for iteration in range(max_iterations):
        log.debug(f"Agent iteration {iteration + 1}/{max_iterations}")
        
        # Call OpenAI with tools
        response = await client.chat.completions.create(
            model=agent_config["model"],
            messages=messages,
            tools=tool_schemas,
            tool_choice="auto"
        )
        
        message = response.choices[0].message
        
        # Check if done (no more tool calls)
        if not message.tool_calls:
            # Parse final move from message.content
            try:
                move_json = json.loads(message.content)
                return move_json
            except json.JSONDecodeError:
                # Try to extract JSON from text
                import re
                json_match = re.search(r'\{.*\}', message.content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                raise ValueError(f"Failed to parse move: {message.content}")
        
        # Execute tool calls
        messages.append(message)  # Add assistant's message with tool_calls
        
        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            
            log.info(f"Agent calling tool: {tool_name}")
            
            try:
                # Execute tool
                result = await executor.execute_tool(tool_name, **tool_args)
                
                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": json.dumps(result)
                })
            except Exception as e:
                log.exception(f"Tool {tool_name} failed: {e}")
                # Add error message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": json.dumps({"error": str(e)})
                })
        
        # Continue loop with tool results
    
    # Max iterations reached
    raise RuntimeError(f"Agent did not produce move within {max_iterations} iterations")
```

### Step 3: Test Basic Agent

```bash
# First install pytest-asyncio
poetry add --group dev pytest-asyncio

# Run simplest test
poetry run pytest tests/test_agent_player.py::TestAgentPromptConstruction::test_agent_system_prompt_includes_available_tools -v
```

### Step 4: Test End-to-End (Manual)

```python
import asyncio
from scrabgpt.core.board import Board
from scrabgpt.core.assets import get_premiums_path
from scrabgpt.core.variant_store import VariantDefinition
from scrabgpt.ai.agent_config import discover_agents, get_default_agents_dir, get_agent_by_name
from scrabgpt.ai.agent_player import propose_move_agent

async def test():
    # Load minimal agent
    agents = discover_agents(get_default_agents_dir())
    agent = get_agent_by_name(agents, "Minimálny Agent")
    
    # Setup board
    board = Board(get_premiums_path())
    rack = ["H", "E", "L", "L", "O", "W", "D"]
    
    # Create variant (simplified)
    from scrabgpt.core.variant_store import get_active_variant_definition
    variant = get_active_variant_definition()
    
    # Propose move
    move = await propose_move_agent(agent, board, rack, variant)
    print("Agent proposed:", move)

asyncio.run(test())
```

---

## 📖 Documentation Map

- **`AGENT_SETUP_SUMMARY.md`** ← You are here - Quick start guide
- **`docs/AGENT_ARCHITECTURE.md`** ← Complete architecture deep dive
- **`agents/README.md`** ← How to create custom agents
- **`AGENTS.md`** ← General project coding guidelines

---

## 🎓 Learning Path

### Beginner: Just Use It
1. Read `AGENT_SETUP_SUMMARY.md`
2. Copy implementation pattern above
3. Test with minimal agent
4. Celebrate! 🎉

### Intermediate: Understand It
1. Read `docs/AGENT_ARCHITECTURE.md`
2. Study test expectations in `tests/test_agent_player.py`
3. Trace through tool execution flow
4. Experiment with different agent configurations

### Advanced: Extend It
1. Add new MCP tools (e.g., `tool_get_blank_positions`)
2. Create custom agents with specific tool subsets
3. Implement dictionary validation (3-tier)
4. Add agent statistics tracking
5. Optimize tool schemas for better AI understanding

---

## 🐛 Common Issues & Solutions

### Import Error: cannot import name 'get_variant_by_slug'

**Fixed!** That import was removed from `mcp_tools.py`.

### pytest.mark.asyncio Unknown Mark

**Solution:**
```bash
poetry add --group dev pytest-asyncio
```

### NotImplementedError when calling propose_move_agent

**Expected!** Follow Step 2 above to implement the function calling loop.

### Agent always returns valid=True for dictionary

**Expected!** Dictionary validation is stub. Implement 3-tier validation or accept stub for now.

### Tool schema has no parameters

**Expected!** `get_tool_schema()` returns basic schema. Enhance by parsing function signatures:

```python
import inspect

def get_tool_schema(tool_name: str) -> dict:
    tool_func = get_tool_function(tool_name)
    sig = inspect.signature(tool_func)
    
    parameters = {}
    for param_name, param in sig.parameters.items():
        # Build parameter schema from type hints
        param_type = param.annotation
        parameters[param_name] = {
            "type": _python_type_to_json_type(param_type),
            "description": f"Parameter {param_name}"
        }
    
    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_func.__doc__.split('\n')[0],
            "parameters": {
                "type": "object",
                "properties": parameters,
                "required": list(sig.parameters.keys())
            }
        }
    }
```

---

## ✨ Success Checklist

Check these off as you complete implementation:

- [ ] OpenAI function calling loop implemented
- [ ] At least one test passes in `test_agent_player.py`
- [ ] Agent can propose valid first move on empty board
- [ ] Tool calls are logged in console
- [ ] Can play full game in agent mode (from UI)
- [ ] Dictionary validation implemented (Slovak)
- [ ] Dictionary validation implemented (English)
- [ ] UI shows opponent mode selector
- [ ] Agent statistics tracked and displayed

---

## 💬 Need Help?

**Stuck on OpenAI function calling?**
- Read official docs: https://platform.openai.com/docs/guides/function-calling
- Check examples: https://github.com/openai/openai-cookbook

**Confused about MCP?**
- Read: https://github.com/mcp-use/mcp-use
- Note: You can implement without mcp-use library (just use OpenAI function calling directly)

**Test failures?**
- Read test docstrings for expected behavior
- Check test fixtures for setup patterns
- Use `pytest -v -s` for verbose output

**Architecture questions?**
- See `docs/AGENT_ARCHITECTURE.md`
- Study existing `player.py` for patterns

---

## 🚀 You're Ready!

Everything is set up. Just implement the OpenAI function calling loop and you'll have a working AI agent that can use tools to reason about Scrabble moves.

**Good luck! 🎯**
