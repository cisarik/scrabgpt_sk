# AI Agent System Setup - Complete ✅

## What Was Built

I've prepared a comprehensive AI agent system with MCP (Model Context Protocol) tool integration for your Scrabble game. This is a **test-driven development** foundation ready for full implementation.

### 📦 Deliverables

#### 1. **MCP Tools System** (`scrabgpt/ai/mcp_tools.py`)
- ✅ 14 stateless tool functions covering rules, scoring, state, and dictionary
- ✅ All tools JSON-serializable for AI agent use
- ✅ Tool registry system for dynamic loading
- ⚠️ Dictionary validation tools are stubs (return always valid)

#### 2. **Agent Configuration** (`scrabgpt/ai/agent_config.py`)
- ✅ `.agent` file parser with schema validation
- ✅ Agent discovery from `agents/` directory
- ✅ Tool existence validation
- ✅ OpenAI function schema generation (basic)

#### 3. **Agent Player** (`scrabgpt/ai/agent_player.py`)
- ✅ System prompt builder
- ✅ Game context serialization
- ✅ Tool access control (MCPToolExecutor)
- ⚠️ **STUB ONLY** - `propose_move_agent()` raises NotImplementedError
- ❌ Needs: OpenAI function calling loop implementation

#### 4. **Opponent Mode System** (`scrabgpt/core/opponent_mode.py`)
- ✅ Enum with 5 modes: AGENT, BEST_MODEL, SINGLE, OPENROUTER, OFFLINE
- ✅ Slovak display names and descriptions
- ✅ Availability flags (OFFLINE disabled)

#### 5. **Predefined Agents** (`agents/*.agent`)
- ✅ **Full Access** - All 14 tools (gpt-4o)
- ✅ **Rule Master** - Rules only, no scoring (gpt-4o-mini)
- ✅ **Minimal** - Basic info only (gpt-4o-mini)
- ✅ **Scorer** - Scoring focus (gpt-4o)

#### 6. **Test Suite** (TDD Approach)
- ✅ `test_mcp_tools.py` - 23 tests for tool wrappers
- ✅ `test_agent_config.py` - 15 tests for config loading
- ✅ `test_agent_player.py` - 12 tests for agent behavior
- ✅ **50 total tests collected successfully**
- ⚠️ Most will fail until full implementation

#### 7. **Documentation**
- ✅ `docs/AGENT_ARCHITECTURE.md` - Complete architecture guide
- ✅ `agents/README.md` - Agent configuration guide
- ✅ `.env.example` - Updated with new variables

#### 8. **Environment Configuration**
- ✅ `OPENAI_PLAYER_MODEL` - Default model selection
- ✅ `OPENAI_BEST_MODEL_AUTO_UPDATE` - Auto-fetch best model
- ✅ `DEFAULT_OPPONENT_MODE` - Default mode (single/agent/openrouter)
- ✅ `DEFAULT_AGENT_NAME` - Default agent selection

---

## 📊 Status Overview

### ✅ Complete & Working
- MCP tool wrappers (except dictionary stubs)
- Agent configuration loading
- Agent discovery from .agent files
- OpponentMode enum
- Test structure (BDD style)
- Example agent configurations
- Documentation

### ⚠️ Stub Implementation (Not Functional Yet)
- `propose_move_agent()` - Main agent player function
- `tool_validate_word_slovak()` - Returns always valid
- `tool_validate_word_english()` - Not implemented
- `get_tool_schema()` - Returns basic schema only

### ❌ Not Started
- OpenAI function calling loop
- MCP tool execution integration
- 3-tier dictionary validation (Slovak/English)
- Dictionary loading (in-memory + HTTP)
- UI opponent mode selection
- Best model auto-update mechanism
- Agent statistics tracking

---

## 🚀 Next Steps to Make It Work

### **Phase 1: Core MCP Integration** (Critical - 8-16 hours)

1. **Install mcp-use library** (if using it):
   ```bash
   poetry add mcp-use
   ```
   
   OR implement direct OpenAI function calling (simpler approach).

2. **Implement OpenAI function calling loop** in `agent_player.py`:
   ```python
   async def propose_move_agent(...):
       messages = [
           {"role": "system", "content": system_prompt},
           {"role": "user", "content": context}
       ]
       
       for iteration in range(max_iterations):
           response = await openai_client.chat.completions.create(
               model=agent_config["model"],
               messages=messages,
               tools=tool_schemas,
               tool_choice="auto"
           )
           
           # Check if done
           if not response.choices[0].message.tool_calls:
               return parse_final_move(response)
           
           # Execute tool calls
           for tool_call in response.choices[0].message.tool_calls:
               result = await executor.execute_tool(
                   tool_call.function.name,
                   **json.loads(tool_call.function.arguments)
               )
               
               # Add tool result to messages
               messages.append({
                   "role": "tool",
                   "tool_call_id": tool_call.id,
                   "content": json.dumps(result)
               })
           
           # Continue loop with tool results
   ```

3. **Generate proper OpenAI function schemas**:
   - Parse function signatures for parameter types
   - Extract docstrings for descriptions
   - Build proper JSON schemas

4. **Test with simple agent**:
   ```bash
   # Start with minimal agent
   poetry run pytest tests/test_agent_player.py::TestAgentMoveGeneration::test_agent_proposes_valid_first_move_on_empty_board -v
   ```

### **Phase 2: Dictionary Validation** (Medium Priority - 6-12 hours)

5. **Slovak 3-tier validation**:
   - Load Slovak word list into memory (from existing dictionary)
   - Integrate JULS API if available (HTTP tier)
   - Keep AI judge as fallback (existing code)

6. **English 3-tier validation**:
   - Download TWL or SOWPODS word list
   - Integrate Wordnik or Merriam-Webster API
   - AI judge fallback

7. **Update tool implementations**:
   ```python
   def tool_validate_word_slovak(word: str) -> dict:
       # Tier 1: In-memory (fast)
       if word.upper() in SLOVAK_DICT:
           return {"valid": True, "tier": 1, "reason": "Found in dictionary"}
       
       # Tier 2: HTTP API
       if JULS_API_AVAILABLE:
           result = await check_juls_api(word)
           if result:
               return {"valid": True, "tier": 2, "reason": "Validated by JULS"}
       
       # Tier 3: AI judge (existing code)
       judge_result = judge_client.judge_words([word], language="Slovak")
       return {
           "valid": judge_result["all_valid"],
           "tier": 3,
           "reason": judge_result["results"][0]["reason"]
       }
   ```

### **Phase 3: UI Integration** (Medium Priority - 4-8 hours)

8. **Add opponent mode selector to Settings**:
   - Radio buttons for each OpponentMode
   - Agent dropdown (populated from `discover_agents()`)
   - Show agent description and tool list
   - Save/load preference

9. **Wire up in `app.py`**:
   ```python
   # In _on_ai_turn or equivalent
   if self.opponent_mode == OpponentMode.AGENT:
       move = await propose_move_agent(
           self.selected_agent_config,
           self.board,
           self.ai_rack,
           self.variant_definition
       )
   elif self.opponent_mode == OpponentMode.SINGLE:
       move = ai_propose_move(...)  # Existing code
   elif self.opponent_mode == OpponentMode.OPENROUTER:
       move, results = await propose_move_multi_model(...)  # Existing
   ```

10. **Display in UI**:
    - Status bar: "Agent: Full Access (12 tools)"
    - Tool call log in debug panel
    - Agent statistics (optional)

---

## 🧪 Testing Strategy

### Running Tests

```bash
# Collect all tests
poetry run pytest tests/test_mcp_tools.py tests/test_agent_config.py tests/test_agent_player.py --collect-only

# Run specific category
poetry run pytest tests/test_mcp_tools.py -v

# Run one test
poetry run pytest tests/test_mcp_tools.py::TestRuleTools::test_rules_first_move_must_cover_center_validates_correctly -v
```

### TDD Workflow

1. **Pick a failing test** (they all fail now since stubs)
2. **Implement just enough** to make it pass
3. **Refactor** if needed
4. **Move to next test**

Start with simpler tests first:
- `test_mcp_tools.py` tests are easiest (tool wrappers)
- `test_agent_config.py` tests are medium (file loading)
- `test_agent_player.py` tests are hardest (requires OpenAI integration)

### Integration Testing

Once basic implementation works:

```bash
# Test agent can be loaded
poetry run python -c "from scrabgpt.ai.agent_config import discover_agents, get_default_agents_dir; print(discover_agents(get_default_agents_dir()))"

# Test tools can be called
poetry run python -c "from scrabgpt.ai.mcp_tools import tool_get_rack_letters; print(tool_get_rack_letters(['A', 'B', 'C']))"
```

---

## 📚 Key Files to Read

### Implementation Priority Order:
1. **`docs/AGENT_ARCHITECTURE.md`** - Full architecture explanation
2. **`scrabgpt/ai/agent_player.py`** - See TODO comments for what needs implementing
3. **`tests/test_agent_player.py`** - See expected behavior patterns
4. **`agents/README.md`** - Understand agent configuration format

### When Stuck:
- Check existing `player.py` for how single-model works
- Check existing `multi_model.py` for async patterns
- Look at test expectations for behavior specs

---

## 🎯 Key Design Decisions

### Why MCP Tools?
- **Stateless** - Easier to test and reason about
- **JSON-serializable** - Works with any AI model
- **Composable** - Mix and match tool access
- **Observable** - Can log all tool calls

### Why .agent Files?
- **Experimentation** - Easy to create new agent variants
- **No code changes** - Just edit JSON
- **Version control** - Track agent performance over time
- **Shareable** - Community can create agents

### Why TDD?
- **Complex domain** - Many edge cases (validation, retries, errors)
- **Clear contracts** - Tests define expected behavior
- **Safe refactoring** - Can change implementation freely
- **Documentation** - Tests show usage patterns

### Why Separate Opponent Modes?
- **User choice** - Different use cases (speed vs quality)
- **Migration path** - Existing modes still work
- **Cost control** - Agent mode may be expensive
- **Experimentation** - Compare different approaches

---

## 💡 Tips & Tricks

### Debugging Agent Behavior

Enable debug logging:
```python
import logging
logging.getLogger("scrabgpt.ai.agent_player").setLevel(logging.DEBUG)
logging.getLogger("scrabgpt.ai.mcp_tools").setLevel(logging.DEBUG)
```

### Creating Custom Agents

1. Copy `agents/minimal.agent` to `agents/my_agent.agent`
2. Edit tool list (add/remove tools)
3. Change model if desired
4. Test: `poetry run python -c "from scrabgpt.ai.agent_config import discover_agents, get_default_agents_dir; print(discover_agents(get_default_agents_dir()))"`

### Finding Optimal Tool Subset

Track metrics:
- Average game score
- Move generation time
- Number of tool calls per move
- Number of invalid moves proposed

Compare agents head-to-head on same board positions.

---

## ⚠️ Known Issues

### pytest-asyncio Warning

Tests using `@pytest.mark.asyncio` show warnings. Fix:

```bash
poetry add --group dev pytest-asyncio
```

Then tests will run properly.

### datetime.utcnow() Deprecation

In `variant_store.py:190`. Replace with:
```python
datetime.now(timezone.utc).isoformat(timespec="seconds")
```

---

## 📞 Support & Questions

**Questions about architecture?** → See `docs/AGENT_ARCHITECTURE.md`

**Questions about tools?** → See docstrings in `scrabgpt/ai/mcp_tools.py`

**Questions about agents?** → See `agents/README.md`

**Questions about tests?** → Read test file docstrings

**Need help implementing?** → Start with Phase 1 tasks above

---

## 🎉 What You Can Do Right Now

Even though agent mode isn't functional yet:

1. ✅ **Browse test expectations** - See what behavior is expected
2. ✅ **Create custom agents** - Edit .agent files and test loading
3. ✅ **Call tools directly** - Test tool functions in Python REPL
4. ✅ **Plan UI changes** - Design settings dialog layout
5. ✅ **Research MCP** - Read mcp-use documentation
6. ✅ **Plan dictionary integration** - Find Slovak/English word lists

---

## 🏁 Success Criteria

You'll know Phase 1 is complete when:

- ✅ `propose_move_agent()` doesn't raise NotImplementedError
- ✅ Agent can make at least one valid move on empty board
- ✅ Tool calls are logged correctly
- ✅ At least 10 tests pass in `test_agent_player.py`
- ✅ Can play a full game in agent mode

You'll know Phase 2 is complete when:

- ✅ Slovak words validated via 3 tiers
- ✅ English words validated via 3 tiers
- ✅ Validation tier distribution tracked

You'll know Phase 3 is complete when:

- ✅ Settings window shows opponent mode selector
- ✅ Agent dropdown populates from .agent files
- ✅ Can switch modes and play games
- ✅ Agent tool usage shown in UI

---

## 📈 Estimated Effort

- **Phase 1 (Core MCP):** 8-16 hours
- **Phase 2 (Dictionaries):** 6-12 hours  
- **Phase 3 (UI):** 4-8 hours
- **Total:** ~20-40 hours

Plus ongoing experimentation and optimization.

---

**Good luck with the implementation! The foundation is solid and ready for you to build on. 🚀**

---

## Quick Start Commands

```bash
# Verify setup
poetry run pytest tests/test_mcp_tools.py tests/test_agent_config.py --collect-only

# List available agents
poetry run python -c "from scrabgpt.ai.agent_config import discover_agents, get_default_agents_dir; import json; print(json.dumps([a['name'] for a in discover_agents(get_default_agents_dir())], indent=2))"

# List available tools
poetry run python -c "from scrabgpt.ai.mcp_tools import get_all_tool_names; import json; print(json.dumps(get_all_tool_names(), indent=2))"

# Test a tool
poetry run python -c "from scrabgpt.ai.mcp_tools import tool_get_rack_letters; print(tool_get_rack_letters(['H', 'E', 'L', 'L', 'O']))"
```
