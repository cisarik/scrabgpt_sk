"""Tests for model selector agent.

This demonstrates TDD for agent systems:
1. Test tools work correctly
2. Test agent logic separately from tools
3. Test end-to-end agent workflow
4. Test error handling
"""

from __future__ import annotations

import pytest
from scrabgpt.ai.model_selector_agent import (
    ModelSelectorAgent,
    SelectionCriteria,
    ModelScore,
)
from scrabgpt.ai.model_fetcher import (
    fetch_openai_models,
    fetch_model_pricing,
    enrich_models_with_pricing,
    get_model_info,
    clear_cache,
    ModelFetchError,
)


class TestModelFetcher:
    """Test the model fetcher tools."""
    
    @pytest.mark.openai
    def test_fetch_openai_models_returns_list(self, openai_api_key):
        """Given: Valid OpenAI API key
        When: Fetching models
        Then: Returns list of model dicts
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        clear_cache()  # Start fresh
        models = fetch_openai_models(openai_api_key, use_cache=False)
        
        assert isinstance(models, list)
        assert len(models) > 0
        
        # Check structure
        first_model = models[0]
        assert "id" in first_model
        assert "created" in first_model
        assert "owned_by" in first_model
    
    @pytest.mark.openai
    def test_fetch_uses_cache(self, openai_api_key):
        """Given: Models fetched once
        When: Fetching again with cache
        Then: Returns cached data without API call
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        clear_cache()
        
        # First fetch
        models1 = fetch_openai_models(openai_api_key, use_cache=True)
        
        # Second fetch (should use cache)
        models2 = fetch_openai_models(openai_api_key, use_cache=True)
        
        # Should be same data
        assert len(models1) == len(models2)
        assert models1[0]["id"] == models2[0]["id"]
    
    def test_fetch_model_pricing_returns_dict(self):
        """Given: No parameters
        When: Fetching pricing
        Then: Returns dict with known models
        """
        pricing = fetch_model_pricing()
        
        assert isinstance(pricing, dict)
        assert "gpt-4o" in pricing
        assert "gpt-4o-mini" in pricing
        
        # Check structure
        gpt4o = pricing["gpt-4o"]
        assert "input_price_per_1m" in gpt4o
        assert "output_price_per_1m" in gpt4o
        assert "context_window" in gpt4o
        assert "tier" in gpt4o
    
    def test_enrich_models_with_pricing_adds_pricing_data(self):
        """Given: Models without pricing
        When: Enriching with pricing
        Then: Models have pricing data attached
        """
        models = [
            {"id": "gpt-4o", "created": 1234567890},
            {"id": "gpt-4o-mini", "created": 1234567890},
        ]
        pricing = fetch_model_pricing()
        
        enriched = enrich_models_with_pricing(models, pricing)
        
        assert len(enriched) == 2
        assert enriched[0]["has_pricing"] is True
        assert "pricing" in enriched[0]
        assert enriched[0]["pricing"]["tier"] == "flagship"
    
    @pytest.mark.openai
    def test_get_model_info_returns_details(self, openai_api_key):
        """Given: Valid model ID
        When: Getting model info
        Then: Returns detailed model info with pricing
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        clear_cache()
        info = get_model_info("gpt-4o", openai_api_key)
        
        assert info["id"] == "gpt-4o"
        assert info["has_pricing"] is True
        assert "pricing" in info
        assert info["pricing"]["tier"] == "flagship"
    
    @pytest.mark.openai
    def test_get_model_info_raises_for_unknown_model(self, openai_api_key):
        """Given: Invalid model ID
        When: Getting model info
        Then: Raises ModelFetchError
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        clear_cache()
        
        with pytest.raises(ModelFetchError, match="Model not found"):
            get_model_info("nonexistent-model-xyz", openai_api_key)


class TestModelSelectorAgentLogic:
    """Test agent logic without API calls (unit tests)."""
    
    def test_agent_initializes_with_config(self):
        """Given: Agent configuration
        When: Creating agent
        Then: Agent is configured correctly
        """
        agent = ModelSelectorAgent(
            criteria=SelectionCriteria.PERFORMANCE,
            exclude_preview=True,
            exclude_legacy=False,
        )
        
        assert agent.criteria == SelectionCriteria.PERFORMANCE
        assert agent.exclude_preview is True
        assert agent.exclude_legacy is False
        assert agent.available_models == []
        assert agent.best_model is None
    
    def test_filter_models_excludes_preview(self):
        """Given: Agent with exclude_preview=True
        When: Filtering models
        Then: Preview models are excluded
        """
        agent = ModelSelectorAgent(exclude_preview=True)
        
        models = [
            {"id": "gpt-4o", "has_pricing": True},
            {"id": "gpt-4-turbo-preview", "has_pricing": True},
            {"id": "o1-preview", "has_pricing": True},
        ]
        
        filtered = agent._filter_models(models)
        
        assert len(filtered) == 1
        assert filtered[0]["id"] == "gpt-4o"
    
    def test_filter_models_excludes_legacy(self):
        """Given: Agent with exclude_legacy=True
        When: Filtering models
        Then: Legacy models are excluded
        """
        agent = ModelSelectorAgent(exclude_legacy=True)
        
        models = [
            {"id": "gpt-4o", "has_pricing": True, "pricing": {"tier": "flagship"}},
            {"id": "gpt-3.5-turbo", "has_pricing": True, "pricing": {"tier": "legacy"}},
        ]
        
        filtered = agent._filter_models(models)
        
        assert len(filtered) == 1
        assert filtered[0]["id"] == "gpt-4o"
    
    def test_calculate_performance_score_flagship_highest(self):
        """Given: Model pricing data
        When: Calculating performance score
        Then: Flagship tier gets highest score
        """
        agent = ModelSelectorAgent()
        
        flagship = {"tier": "flagship", "context_window": 128000, "max_output_tokens": 16384}
        legacy = {"tier": "legacy", "context_window": 16385, "max_output_tokens": 4096}
        
        flagship_score = agent._calculate_performance_score(flagship)
        legacy_score = agent._calculate_performance_score(legacy)
        
        assert flagship_score > legacy_score
        assert flagship_score >= 100  # Should hit max
    
    def test_calculate_cost_score_cheaper_higher(self):
        """Given: Model pricing data
        When: Calculating cost score
        Then: Cheaper models get higher scores
        """
        agent = ModelSelectorAgent()
        
        expensive = {"input_price_per_1m": 10.0, "output_price_per_1m": 30.0}
        cheap = {"input_price_per_1m": 0.15, "output_price_per_1m": 0.60}
        
        expensive_score = agent._calculate_cost_score(expensive)
        cheap_score = agent._calculate_cost_score(cheap)
        
        assert cheap_score > expensive_score


class TestModelSelectorAgentWorkflow:
    """Test end-to-end agent workflow."""
    
    @pytest.mark.openai
    def test_agent_selects_best_model_performance_criteria(self, openai_api_key):
        """Given: Agent with PERFORMANCE criteria
        When: Selecting best model
        Then: Returns flagship model (gpt-4o or similar)
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        clear_cache()
        agent = ModelSelectorAgent(
            api_key=openai_api_key,
            criteria=SelectionCriteria.PERFORMANCE,
            exclude_preview=True,
            exclude_legacy=True,
        )
        
        best = agent.select_best_model()
        
        assert isinstance(best, ModelScore)
        assert best.model_id  # Should have selected something
        assert best.total_score > 0
        
        # With PERFORMANCE criteria, should select a flagship model
        assert "gpt-4" in best.model_id.lower() or "o1" in best.model_id.lower()
        
        # Should have reasoning
        assert len(best.reasoning) > 0
        assert "Tier:" in best.reasoning
    
    @pytest.mark.openai
    def test_agent_selects_best_model_cost_criteria(self, openai_api_key):
        """Given: Agent with COST criteria
        When: Selecting best model
        Then: Returns affordable model (gpt-4o-mini or similar)
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        clear_cache()
        agent = ModelSelectorAgent(
            api_key=openai_api_key,
            criteria=SelectionCriteria.COST,
            exclude_preview=True,
            exclude_legacy=True,
        )
        
        best = agent.select_best_model()
        
        assert isinstance(best, ModelScore)
        
        # With COST criteria, should select an affordable model
        # gpt-4o-mini is typically the best cost/performance
        assert "mini" in best.model_id.lower() or best.cost_score > 80
    
    @pytest.mark.openai
    def test_agent_returns_top_n_models(self, openai_api_key):
        """Given: Agent has selected best model
        When: Getting top N models
        Then: Returns sorted list of top models
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        clear_cache()
        agent = ModelSelectorAgent(
            api_key=openai_api_key,
            criteria=SelectionCriteria.BALANCED,
        )
        
        agent.select_best_model()
        top_5 = agent.get_top_n_models(5)
        
        assert len(top_5) <= 5
        assert all(isinstance(s, ModelScore) for s in top_5)
        
        # Should be sorted by score
        scores = [s.total_score for s in top_5]
        assert scores == sorted(scores, reverse=True)
    
    @pytest.mark.openai
    def test_agent_explains_selection(self, openai_api_key):
        """Given: Agent has selected best model
        When: Getting explanation
        Then: Returns detailed explanation string
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        clear_cache()
        agent = ModelSelectorAgent(
            api_key=openai_api_key,
            criteria=SelectionCriteria.BALANCED,
        )
        
        agent.select_best_model()
        explanation = agent.explain_selection()
        
        assert isinstance(explanation, str)
        assert "MODEL SELECTION REPORT" in explanation
        assert "SELECTED:" in explanation
        assert agent.best_model.model_id in explanation
        assert "TOP 5 MODELS:" in explanation
    
    @pytest.mark.openai
    def test_agent_handles_no_suitable_models(self, openai_api_key):
        """Given: Agent with very restrictive filters
        When: Selecting best model
        Then: Raises ModelFetchError
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        clear_cache()
        
        # Create agent that excludes everything
        agent = ModelSelectorAgent(
            api_key=openai_api_key,
            exclude_preview=True,
            exclude_legacy=True,
        )
        
        # Manually filter to empty list
        agent._filter_models = lambda models: []
        
        with pytest.raises(ModelFetchError, match="No suitable models found"):
            agent.select_best_model()


class TestAgentIntegration:
    """Integration tests for real-world usage."""
    
    @pytest.mark.openai
    @pytest.mark.stress
    def test_agent_performance_vs_cost_comparison(self, openai_api_key):
        """Stress test: Compare different selection criteria.
        
        This is a learning test that shows how criteria affect selection.
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        clear_cache()
        
        # Test all three criteria
        criteria_list = [
            SelectionCriteria.PERFORMANCE,
            SelectionCriteria.COST,
            SelectionCriteria.BALANCED,
        ]
        
        results = {}
        
        for criteria in criteria_list:
            agent = ModelSelectorAgent(
                api_key=openai_api_key,
                criteria=criteria,
                exclude_preview=True,
                exclude_legacy=True,
            )
            
            best = agent.select_best_model()
            results[criteria.value] = {
                "model": best.model_id,
                "score": best.total_score,
                "performance_score": best.performance_score,
                "cost_score": best.cost_score,
            }
            
            print(f"\n{criteria.value.upper()}:")
            print(f"  Model: {best.model_id}")
            print(f"  Total Score: {best.total_score:.2f}")
            print(f"  Performance: {best.performance_score:.2f}")
            print(f"  Cost: {best.cost_score:.2f}")
        
        # Performance criteria should select more capable model
        assert results["performance"]["performance_score"] >= results["cost"]["performance_score"]
        
        # Cost criteria should select cheaper model
        assert results["cost"]["cost_score"] >= results["performance"]["cost_score"]
        
        # Balanced should be in between
        balanced_perf = results["balanced"]["performance_score"]
        balanced_cost = results["balanced"]["cost_score"]
        
        # Balanced shouldn't be worst in either category
        assert balanced_perf > min(results["performance"]["performance_score"], results["cost"]["performance_score"]) * 0.8
        assert balanced_cost > min(results["performance"]["cost_score"], results["cost"]["cost_score"]) * 0.8
