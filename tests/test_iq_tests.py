"""IQ Tests / Stress Tests for AI validation.

These tests load user-created IQ test scenarios from tests/iq_tests/ directory
and validate AI behavior against expected outcomes.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from typing import Any

# IQ tests directory
IQ_TESTS_DIR = Path(__file__).parent / "iq_tests"


def load_iq_tests() -> list[tuple[str, dict[str, Any]]]:
    """Load all .iq.json files from iq_tests directory.
    
    Returns:
        List of (test_id, test_data) tuples
    """
    if not IQ_TESTS_DIR.exists():
        return []
    
    tests = []
    for iq_file in IQ_TESTS_DIR.glob("*.iq.json"):
        try:
            with open(iq_file, "r", encoding="utf-8") as f:
                test_data = json.load(f)
                test_id = iq_file.stem
                tests.append((test_id, test_data))
        except Exception as e:
            pytest.fail(f"Failed to load IQ test {iq_file}: {e}")
    
    return tests


# Parametrize all IQ tests
iq_tests = load_iq_tests()
test_ids = [test_id for test_id, _ in iq_tests]
test_data = [data for _, data in iq_tests]


class TestIQTests:
    """Run IQ tests / stress tests for AI validation."""
    
    @pytest.mark.stress
    @pytest.mark.parametrize("test_data", test_data, ids=test_ids)
    def test_iq_scenario_structure(self, test_data: dict[str, Any]) -> None:
        """Validate IQ test file structure.
        
        Given: IQ test JSON file
        When: Loading test data
        Then: All required fields are present
        """
        required_fields = ["name", "description", "difficulty", "scenario", "validation"]
        
        for field in required_fields:
            assert field in test_data, f"Missing required field: {field}"
        
        assert test_data["difficulty"] in ["easy", "medium", "hard", "expert"]
        
        # Validate scenario structure
        scenario = test_data["scenario"]
        assert "board_state" in scenario
        assert "rack" in scenario
        assert isinstance(scenario["rack"], list)
        
        # Validate validation structure  
        validation = test_data["validation"]
        assert "judge_calls" in validation or "scoring" in validation or "rules" in validation
    
    @pytest.mark.stress
    @pytest.mark.openai
    @pytest.mark.parametrize("test_data", test_data, ids=test_ids)
    async def test_iq_judge_validation(
        self, 
        test_data: dict[str, Any],
        openai_api_key: str | None
    ) -> None:
        """Test judge validation against IQ test expectations.
        
        Given: IQ test with judge_calls validation
        When: Calling judge with test words
        Then: Judge responses match expected validity
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        validation = test_data.get("validation", {})
        judge_calls = validation.get("judge_calls", [])
        
        if not judge_calls:
            pytest.skip("No judge_calls in this IQ test")
        
        from scrabgpt.ai.client import OpenAIClient
        
        client = OpenAIClient()
        
        for call in judge_calls:
            word = call["word"]
            expected_valid = call["expected_valid"]
            language = call.get("language", "English")
            
            result = client.judge_words([word], language=language)
            
            actual_valid = result.get("all_valid", False)
            
            assert actual_valid == expected_valid, (
                f"Judge validation mismatch for '{word}': "
                f"expected {expected_valid}, got {actual_valid}. "
                f"Reason: {result.get('results', [{}])[0].get('reason', 'unknown')}"
            )
    
    @pytest.mark.stress
    @pytest.mark.parametrize("test_data", test_data, ids=test_ids)
    def test_iq_scoring_calculation(self, test_data: dict[str, Any]) -> None:
        """Test scoring calculation against IQ test expectations.
        
        Given: IQ test with scoring validation
        When: Calculating score for expected move
        Then: Score is within expected range
        """
        validation = test_data.get("validation", {})
        scoring = validation.get("scoring", {})
        
        if not scoring:
            pytest.skip("No scoring validation in this IQ test")
        
        # TODO: Implement scoring calculation test
        # This requires:
        # 1. Parse board_state from scenario
        # 2. Parse rack
        # 3. Calculate score for expected move
        # 4. Compare with expected_min and expected_max
        
        pytest.skip("Scoring calculation test not yet implemented")
    
    @pytest.mark.stress
    @pytest.mark.openai
    @pytest.mark.parametrize("test_data", test_data, ids=test_ids)
    async def test_iq_ai_move_quality(
        self,
        test_data: dict[str, Any],
        openai_api_key: str | None
    ) -> None:
        """Test AI move generation quality against IQ test expectations.
        
        Given: IQ test with expected_behavior
        When: AI generates move for scenario
        Then: Move meets quality expectations (score, validity, etc.)
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        scenario = test_data.get("scenario", {})
        expected_behavior = scenario.get("expected_behavior", {})
        
        if not expected_behavior:
            pytest.skip("No expected_behavior in this IQ test")
        
        # TODO: Implement AI move generation test
        # This requires:
        # 1. Create board from board_state
        # 2. Create rack from rack list
        # 3. Call AI player to generate move
        # 4. Validate move meets expectations
        
        pytest.skip("AI move generation test not yet implemented")


# Utility function to create IQ tests (for future UI integration)
def create_iq_test(
    name: str,
    description: str,
    difficulty: str,
    board_state: str,
    rack: list[str],
    expected_behavior: dict[str, Any],
    validation: dict[str, Any],
    tags: list[str] | None = None,
    author: str = "user",
) -> Path:
    """Create a new IQ test file.
    
    Args:
        name: Test name
        description: Test description
        difficulty: easy, medium, hard, expert
        board_state: Board state (e.g., "empty", or serialized board)
        rack: List of letters in rack
        expected_behavior: Expected AI behavior dict
        validation: Validation rules dict
        tags: Optional list of tags
        author: Test author
    
    Returns:
        Path to created IQ test file
    """
    import datetime
    
    test_data = {
        "name": name,
        "description": description,
        "difficulty": difficulty,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "author": author,
        "scenario": {
            "board_state": board_state,
            "rack": rack,
            "expected_behavior": expected_behavior,
        },
        "validation": validation,
        "tags": tags or [],
    }
    
    # Generate filename from name
    filename = name.lower().replace(" ", "_")
    filename = "".join(c for c in filename if c.isalnum() or c == "_")
    filename = f"{filename}.iq.json"
    
    output_path = IQ_TESTS_DIR / filename
    IQ_TESTS_DIR.mkdir(exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(test_data, f, indent=2, ensure_ascii=False)
    
    return output_path
