# Agent Pattern Tutorial - Model Selector Example

This tutorial explains the **Agent Pattern** using the Model Selector Agent as a real-world example. This agent selects the best OpenAI model based on criteria like performance, cost, and availability.

## What is an Agent?

An **agent** is a software system that:
1. Has **TOOLS** - Functions it can call to interact with the world
2. Has **LOGIC** - Decision-making process to achieve a goal  
3. Has **STATE** - Memory of what it has tried/learned
4. Is **AUTONOMOUS** - Makes decisions without constant human input

Think of it like a human agent (travel agent, real estate agent):
- **Tools**: Phone, computer, databases
- **Logic**: Experience and training
- **State**: Notes, memory
- **Autonomy**: Makes decisions within their domain

## Agent Types

### 1. Rule-Based Agent (What We Built)
- Uses **predefined rules** for decision-making
- Fast, deterministic, predictable
- Example: Model Selector Agent

### 2. LLM-Based Agent (Future)
- Uses **Language Model** for decision-making
- Flexible, handles novel situations
- Example: Gameplay Agent (uses OpenAI to decide actions)

## Our Example: Model Selector Agent

### Goal
**Select the best OpenAI model for ScrabGPT based on performance, cost, and availability.**

### Components

#### 1. TOOLS (Functions to Interact with World)

Located in `scrabgpt/ai/model_fetcher.py`:

```python
# Tool 1: Fetch available models from OpenAI
def fetch_openai_models(api_key: str) -> list[dict]:
    """Fetch all available OpenAI models."""
    client = OpenAI(api_key=api_key)
    response = client.models.list()
    return [model.dict() for model in response.data]

# Tool 2: Get pricing information
def fetch_model_pricing() -> dict[str, dict]:
    """Get OpenAI model pricing information."""
    return {
        "gpt-4o": {
            "input_price_per_1m": 2.50,
            "output_price_per_1m": 10.00,
            "tier": "flagship"
        },
        # ... more models
    }

# Tool 3: Enrich models with pricing
def enrich_models_with_pricing(models: list, pricing: dict) -> list:
    """Add pricing data to models."""
    # Match models with pricing info
    # ...
```

**Key Insight**: Tools are just functions. The agent calls them to gather information.

#### 2. LOGIC (Decision-Making Process)

Located in `scrabgpt/ai/model_selector_agent.py`:

```python
class ModelSelectorAgent:
    """Agent that selects best model based on criteria."""
    
    def select_best_model(self) -> ModelScore:
        """Main decision-making workflow."""
        
        # Step 1: Gather information (use tools)
        models = self._fetch_and_enrich_models()
        
        # Step 2: Filter options (apply rules)
        filtered = self._filter_models(models)
        
        # Step 3: Score options (evaluate each)
        scores = self._score_models(filtered)
        
        # Step 4: Select best (make decision)
        best = max(scores, key=lambda s: s.total_score)
        
        # Step 5: Return with reasoning
        return best
```

**Key Insight**: The workflow is explicit and testable. Each step is a method you can test independently.

#### 3. STATE (Memory)

```python
class ModelSelectorAgent:
    def __init__(self, criteria: SelectionCriteria):
        # Configuration
        self.criteria = criteria
        
        # State (what the agent remembers)
        self.available_models: list = []
        self.model_scores: list[ModelScore] = []
        self.best_model: ModelScore | None = None
```

**Key Insight**: State is just instance variables. The agent remembers what it has learned.

#### 4. AUTONOMY (Independent Decision-Making)

The agent makes decisions based on:
- **Configured criteria** (performance, cost, balanced)
- **Available data** (models and pricing)
- **Built-in logic** (scoring algorithm)

No human intervention needed during execution!

## Deep Dive: The Scoring Algorithm

This is where the "intelligence" lives:

```python
def _score_models(self, models: list) -> list[ModelScore]:
    """Score each model based on criteria."""
    
    # Define weights based on criteria
    if self.criteria == SelectionCriteria.PERFORMANCE:
        perf_weight, cost_weight = 0.7, 0.2  # Prioritize performance
    elif self.criteria == SelectionCriteria.COST:
        perf_weight, cost_weight = 0.2, 0.7  # Prioritize cost
    else:  # BALANCED
        perf_weight, cost_weight = 0.4, 0.4  # Balance both
    
    scores = []
    for model in models:
        # Calculate performance score (0-100)
        perf_score = self._calculate_performance_score(model["pricing"])
        
        # Calculate cost score (0-100, higher = cheaper)
        cost_score = self._calculate_cost_score(model["pricing"])
        
        # Weighted total
        total = perf_score * perf_weight + cost_score * cost_weight
        
        scores.append(ModelScore(
            model_id=model["id"],
            total_score=total,
            # ... more fields
        ))
    
    return sorted(scores, key=lambda s: s.total_score, reverse=True)
```

### Performance Scoring

```python
def _calculate_performance_score(self, pricing: dict) -> float:
    """Calculate performance based on tier and capabilities."""
    
    # Tier scoring (flagship > reasoning > premium > efficient > legacy)
    tier_scores = {
        "flagship": 100,
        "reasoning": 90,
        "premium": 70,
        "efficient": 60,
        "legacy": 30,
    }
    tier_score = tier_scores[pricing["tier"]]
    
    # Bonus for large context window (normalize to 128k)
    context_bonus = min(pricing["context_window"] / 128000 * 20, 20)
    
    # Bonus for high max output (normalize to 16k)
    output_bonus = min(pricing["max_output_tokens"] / 16384 * 10, 10)
    
    return min(tier_score + context_bonus + output_bonus, 100.0)
```

### Cost Scoring

```python
def _calculate_cost_score(self, pricing: dict) -> float:
    """Calculate cost score (higher score = cheaper model)."""
    
    # Total cost (input + output)
    total_cost = (pricing["input_price_per_1m"] + pricing["output_price_per_1m"]) / 2
    
    # Inverse scoring: cheaper = higher score
    max_cost = 30.0  # Most expensive we consider
    min_cost = 0.1   # Cheapest possible
    
    if total_cost >= max_cost:
        return 0.0  # Too expensive
    elif total_cost <= min_cost:
        return 100.0  # Super cheap!
    else:
        # Linear inverse scale
        return 100.0 * (1 - (total_cost - min_cost) / (max_cost - min_cost))
```

**Key Insight**: The scoring algorithm encodes domain knowledge (what makes a model "good"). This is where you embed expertise!

## Testing an Agent

Agents should be tested at multiple levels:

### Level 1: Test Tools (Unit Tests)

```python
def test_fetch_openai_models_returns_list(openai_api_key):
    """Test that tool works correctly."""
    models = fetch_openai_models(openai_api_key)
    
    assert isinstance(models, list)
    assert len(models) > 0
    assert "id" in models[0]
```

### Level 2: Test Logic (Unit Tests)

```python
def test_calculate_performance_score_flagship_highest():
    """Test scoring logic without API calls."""
    agent = ModelSelectorAgent()
    
    flagship = {"tier": "flagship", "context_window": 128000}
    legacy = {"tier": "legacy", "context_window": 16385}
    
    flagship_score = agent._calculate_performance_score(flagship)
    legacy_score = agent._calculate_performance_score(legacy)
    
    assert flagship_score > legacy_score
```

### Level 3: Test Workflow (Integration Tests)

```python
@pytest.mark.openai
def test_agent_selects_best_model_performance_criteria(openai_api_key):
    """Test end-to-end workflow with real API."""
    agent = ModelSelectorAgent(
        api_key=openai_api_key,
        criteria=SelectionCriteria.PERFORMANCE,
    )
    
    best = agent.select_best_model()
    
    # With PERFORMANCE criteria, should select flagship model
    assert "gpt-4" in best.model_id.lower()
```

## Auto-Update Mechanism

The agent enables automatic model updates:

```python
# Located in scrabgpt/ai/model_auto_updater.py

def check_and_update_model() -> dict:
    """Check for best model and update .env if needed."""
    
    # 1. Get current model from .env
    current_model = os.getenv("OPENAI_PLAYER_MODEL")
    
    # 2. Use agent to find best model
    agent = ModelSelectorAgent(criteria=SelectionCriteria.BALANCED)
    best = agent.select_best_model()
    
    # 3. Update .env if different
    if best.model_id != current_model:
        update_env_file("OPENAI_PLAYER_MODEL", best.model_id)
        return {"updated": True, "new_model": best.model_id}
    
    return {"updated": False}
```

**Key Insight**: Agents can automate decisions that humans would normally make manually!

## UI Integration

The UI displays the current model and provides manual check:

```python
# Located in scrabgpt/ui/model_display_widget.py

class ModelDisplayWidget(QWidget):
    """Widget showing current model (bold green) with check button."""
    
    def _on_check_clicked(self):
        """User clicked "Check for Best" button."""
        
        # Run agent in background thread
        result = check_and_update_model(force=True)
        
        if result["changed"]:
            # Show dialog: "Better model available: gpt-4o"
            # Ask user to confirm update
```

## Learning Exercises

### Exercise 1: Add New Criteria
Add a new selection criteria: `RELIABILITY` that prioritizes stable, non-preview models.

**Hint**: Modify `SelectionCriteria` enum and add weights in `_score_models()`.

### Exercise 2: Add Context Window Requirement
Add a minimum context window requirement (e.g., 32k) to the agent.

**Hint**: Add `min_context_window` parameter to `__init__()` and filter in `_filter_models()`.

### Exercise 3: Add Price Budget
Add a maximum monthly budget and calculate which model gives best performance within budget.

**Hint**: Add `monthly_budget` parameter and estimate usage to filter models.

### Exercise 4: Multi-Criteria Optimization
Implement Pareto frontier analysis to show trade-offs between cost and performance.

**Hint**: Calculate Pareto optimal models and return top N on the frontier.

## Agent Pattern Summary

| Component | Purpose | Example |
|-----------|---------|---------|
| **Tools** | Interact with world | `fetch_openai_models()` |
| **Logic** | Make decisions | `_score_models()` |
| **State** | Remember information | `self.model_scores` |
| **Autonomy** | Independent operation | `select_best_model()` |

### When to Use Agents

✅ **Use agents when:**
- Task requires multiple steps
- Decisions need consistent logic
- Process should be automated
- Domain knowledge can be encoded

❌ **Don't use agents when:**
- Single API call suffices
- Process needs human judgment
- Requirements change constantly
- Simpler approach works fine

## Next Steps

1. **Read the code**: Start with `model_selector_agent.py`
2. **Run the tests**: `poetry run pytest tests/test_model_selector_agent.py -v`
3. **Try the agent**: See `QUICK_AGENT_DEMO.md` for interactive example
4. **Modify the agent**: Try the learning exercises above
5. **Build your own**: Create an agent for a different task!

## Resources

- **Code**: `scrabgpt/ai/model_selector_agent.py`
- **Tests**: `tests/test_model_selector_agent.py`
- **Tools**: `scrabgpt/ai/model_fetcher.py`
- **Auto-update**: `scrabgpt/ai/model_auto_updater.py`
- **UI**: `scrabgpt/ui/model_display_widget.py`

## Conclusion

The agent pattern is powerful for automating complex decision-making. Key takeaways:

1. **Separate tools from logic** - Tools gather data, logic makes decisions
2. **Make logic explicit** - Each step should be testable
3. **Encode domain knowledge** - Scoring algorithms embed expertise
4. **Test at multiple levels** - Unit test logic, integration test workflow
5. **Provide reasoning** - Always explain why a decision was made

You've now seen a complete agent implementation. Use this pattern for any complex decision-making task!
