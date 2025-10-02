from __future__ import annotations

from unittest.mock import MagicMock, patch

from scrabgpt.ai.client import OpenAIClient


def test_maximalisticky_found_in_juls_online() -> None:
    """Test that 'maximalistický' is validated via JÚĽŠ online without OpenAI.
    
    This tests the 3-tier validation:
    1. Local dictionary: not found (simulated by mock)
    2. JÚĽŠ online: found (real HTTP call)
    3. OpenAI: not called (verified by mock)
    """
    client = OpenAIClient()
    
    # Mock the local dictionary to return False for maximalistický
    # (simulating that it's not in sk.sorted.txt)
    mock_dict = MagicMock(return_value=False)
    client._slovak_dict = mock_dict
    
    # Mock _judge_with_openai to ensure it's never called
    with patch.object(client, '_judge_with_openai') as mock_openai:
        # Set up the mock to raise an error if called
        mock_openai.side_effect = AssertionError(
            "OpenAI should not be called! Word should be found in JÚĽŠ online."
        )
        
        # Test the word
        result = client.judge_words(["maximalistický"], language="Slovak")
        
        # Verify results
        assert result["all_valid"] is True
        assert len(result["results"]) == 1
        
        entry = result["results"][0]
        assert entry["word"] == "maximalistický"
        assert entry["valid"] is True
        assert "JÚĽŠ" in entry["reason"] or "slovník" in entry["reason"].lower()
        
        # Verify local dict was checked
        mock_dict.assert_called_once_with("maximalistický")
        
        # Verify OpenAI was NOT called
        mock_openai.assert_not_called()


def test_multiple_words_tiered_validation() -> None:
    """Test multiple words going through different validation tiers.
    
    - voda: should be in local dictionary (tier 1)
    - maximalistický: should be in JÚĽŠ online (tier 2)
    - Made-up word would go to OpenAI (tier 3) - not tested here
    """
    client = OpenAIClient()
    
    # Create a mock that returns True only for "voda" (simulating local dict)
    def mock_dict_lookup(word: str) -> bool:
        return word.lower() == "voda"
    
    client._slovak_dict = mock_dict_lookup
    
    # Mock _judge_with_openai to ensure it's never called for valid words
    with patch.object(client, '_judge_with_openai') as mock_openai:
        mock_openai.side_effect = AssertionError(
            "OpenAI should not be called for words in dictionaries!"
        )
        
        result = client.judge_words(["voda", "maximalistický"], language="Slovak")
        
        # Both should be valid
        assert result["all_valid"] is True
        assert len(result["results"]) == 2
        
        # Find each word in results
        voda_result = next(r for r in result["results"] if r["word"] == "voda")
        max_result = next(r for r in result["results"] if r["word"] == "maximalistický")
        
        # voda should be from local dictionary
        assert voda_result["valid"] is True
        assert "oficiálnom slovenskom slovníku" in voda_result["reason"]
        
        # maximalistický should be from JÚĽŠ online
        assert max_result["valid"] is True
        assert "JÚĽŠ" in max_result["reason"] or "online" in max_result["reason"].lower()
        
        # OpenAI should not be called
        mock_openai.assert_not_called()
