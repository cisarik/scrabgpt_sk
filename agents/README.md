# Agent Configurations

This directory contains `.agent` configuration files that define AI agents with different tool access levels.

## Agent Format

Each `.agent` file is a JSON file with the following structure:

```json
{
  "name": "Agent Name",
  "description": "Description of agent capabilities",
  "model": "gpt-4o",
  "tools": [
    "tool_name_1",
    "tool_name_2",
    ...
  ]
}
```

## Fields

- **name** (required): Display name of the agent
- **description** (required): Human-readable description of what tools this agent has
- **model** (required): OpenAI model to use (e.g., "gpt-4o", "gpt-4o-mini")
- **tools** (required): List of tool names this agent can access

## Available Tools

### Rule Validation Tools
- `rules_first_move_must_cover_center` - Check if first move covers center
- `rules_placements_in_line` - Check if placements form a line
- `rules_connected_to_existing` - Check if placements connect to board
- `rules_no_gaps_in_line` - Check for gaps in placement line
- `rules_extract_all_words` - Extract all words formed

### Scoring Tools
- `scoring_score_words` - Calculate score with premium breakdown
- `calculate_move_score` - High-level: extract words + score them

### Information Tools
- `get_board_state` - Get current board grid
- `get_rack_letters` - Get available letters
- `get_premium_squares` - Get unused premium squares
- `get_tile_values` - Get point values for letters

### Dictionary Tools
- `validate_word_slovak` - Validate Slovak words (3-tier)
- `validate_word_english` - Validate English words (3-tier) [Not implemented]

### Composite Tools
- `validate_move_legality` - Complete move validation (all rules)
- `calculate_move_score` - Complete scoring (words + score)

## Predefined Agents

### Full Access (full_access.agent)
Has access to all tools. Best performance but may be slower due to many tool calls.

### Rule Master (rule_master.agent)
Has all rule validation tools but no scoring tools. Must estimate scores mentally.

### Minimal (minimal.agent)
Only basic information and validation. Most challenging for the AI.

### Scorer (scorer.agent)
Focused on scoring - sees premiums and calculates exact scores but limited rule tools.

## Creating Custom Agents

1. Create a new `.agent` file in this directory
2. Follow the JSON structure above
3. Choose tools from the available list
4. Test by selecting the agent in Settings
5. Compare performance against other agents

## Experimental: Finding Optimal Tool Set

The goal is to discover which combination of tools produces the best gameplay:
- Too many tools → slower, more API calls
- Too few tools → poor move quality

Try different combinations and track:
- Average score per game
- Move generation time
- Number of invalid moves proposed
- Win rate against other agents

## Notes

- Agent selection is saved in game state
- Each agent uses the specified model (cost varies)
- Tools are enforced - agents cannot access tools not in their list
- Invalid tool names will cause agent loading to fail
