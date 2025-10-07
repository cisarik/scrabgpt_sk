"""Agent for selecting the best OpenAI model.

This is a learning example of the Agent pattern in ScrabGPT.

AGENT PATTERN EXPLAINED:
========================

An agent is a system that:
1. Has TOOLS - Functions it can call to interact with the world
2. Has LOGIC - Decision-making process to achieve a goal
3. Has STATE - Memory of what it has tried
4. Is AUTONOMOUS - Makes decisions without constant human input

In this example:
- TOOLS: fetch_openai_models(), fetch_model_pricing(), get_model_info()
- LOGIC: Evaluate models based on criteria (performance, cost, availability)
- STATE: Cache of fetched models, scoring results
- GOAL: Determine the "best" model for ScrabGPT gameplay

The agent doesn't use LLM - it's pure logic. More advanced agents 
(like the gameplay agent) use LLM to make decisions.
"""

from __future__ import annotations

import logging
from typing import Any
from dataclasses import dataclass
from enum import Enum

from .model_fetcher import (
    fetch_openai_models,
    fetch_model_pricing,
    enrich_models_with_pricing,
    ModelFetchError,
)

log = logging.getLogger("scrabgpt.ai.model_selector_agent")


class SelectionCriteria(Enum):
    """Criteria for selecting the best model."""
    PERFORMANCE = "performance"  # Prioritize capability over cost
    COST = "cost"  # Prioritize cost over capability
    BALANCED = "balanced"  # Balance cost and capability


@dataclass
class ModelScore:
    """Score for a model based on selection criteria."""
    model_id: str
    total_score: float
    performance_score: float
    cost_score: float
    availability_score: float
    reasoning: str


class ModelSelectorAgent:
    """Agent that selects the best OpenAI model based on criteria.
    
    This agent demonstrates the basic agent pattern:
    1. Initialize with configuration
    2. Use tools to gather information
    3. Process information with logic
    4. Make a decision
    5. Return result with reasoning
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        criteria: SelectionCriteria = SelectionCriteria.BALANCED,
        exclude_preview: bool = True,
        exclude_legacy: bool = True,
    ):
        """Initialize the model selector agent.
        
        Args:
            api_key: OpenAI API key
            criteria: Selection criteria (performance, cost, balanced)
            exclude_preview: Exclude preview/beta models
            exclude_legacy: Exclude legacy models (gpt-3.5-turbo, etc.)
        """
        self.api_key = api_key
        self.criteria = criteria
        self.exclude_preview = exclude_preview
        self.exclude_legacy = exclude_legacy
        
        # State (what the agent remembers)
        self.available_models: list[dict[str, Any]] = []
        self.model_scores: list[ModelScore] = []
        self.best_model: ModelScore | None = None
    
    def select_best_model(self) -> ModelScore:
        """Select the best model based on criteria.
        
        This is the main agent workflow:
        1. Gather information (fetch models + pricing)
        2. Filter models (apply exclusions)
        3. Score models (evaluate each one)
        4. Select best (highest score)
        5. Return result with reasoning
        
        Returns:
            ModelScore with best model selection
        
        Raises:
            ModelFetchError: If no suitable models found
        """
        log.info("Starting model selection with criteria: %s", self.criteria.value)
        
        # Step 1: Gather information
        models = self._fetch_and_enrich_models()
        log.info("Fetched %d models", len(models))
        
        # Step 2: Filter models
        filtered = self._filter_models(models)
        log.info("Filtered to %d suitable models", len(filtered))
        
        if not filtered:
            raise ModelFetchError("No suitable models found after filtering")
        
        # Step 3: Score models
        scores = self._score_models(filtered)
        self.model_scores = scores
        
        # Step 4: Select best
        best = max(scores, key=lambda s: s.total_score)
        self.best_model = best
        
        log.info(
            "Selected best model: %s (score: %.2f)",
            best.model_id,
            best.total_score
        )
        log.debug("Reasoning: %s", best.reasoning)
        
        return best
    
    def _fetch_and_enrich_models(self) -> list[dict[str, Any]]:
        """Fetch models and enrich with pricing (TOOL usage)."""
        models = fetch_openai_models(self.api_key)
        pricing = fetch_model_pricing()
        enriched = enrich_models_with_pricing(models, pricing)
        self.available_models = enriched
        return enriched
    
    def _filter_models(self, models: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter models based on agent configuration (LOGIC)."""
        filtered = models
        
        # Exclude models without pricing
        filtered = [m for m in filtered if m.get("has_pricing", False)]
        
        # Exclude preview models if configured
        if self.exclude_preview:
            filtered = [
                m for m in filtered
                if not any(kw in m["id"].lower() for kw in ["preview", "beta"])
            ]
        
        # Exclude legacy models if configured
        if self.exclude_legacy:
            filtered = [
                m for m in filtered
                if m.get("pricing", {}).get("tier") != "legacy"
            ]
        
        return filtered
    
    def _score_models(self, models: list[dict[str, Any]]) -> list[ModelScore]:
        """Score each model based on criteria (LOGIC).
        
        Scoring algorithm:
        - Performance: Based on tier (flagship > reasoning > premium > efficient)
        - Cost: Inverse of price (cheaper = higher score)
        - Availability: Binary (has pricing info or not)
        
        Weights depend on criteria:
        - PERFORMANCE: 70% performance, 20% cost, 10% availability
        - COST: 20% performance, 70% cost, 10% availability
        - BALANCED: 40% performance, 40% cost, 20% availability
        """
        scores = []
        
        # Define weights based on criteria
        if self.criteria == SelectionCriteria.PERFORMANCE:
            perf_weight, cost_weight, avail_weight = 0.7, 0.2, 0.1
        elif self.criteria == SelectionCriteria.COST:
            perf_weight, cost_weight, avail_weight = 0.2, 0.7, 0.1
        else:  # BALANCED
            perf_weight, cost_weight, avail_weight = 0.4, 0.4, 0.2
        
        for model in models:
            model_id = model["id"]
            pricing = model.get("pricing", {})
            
            # Performance score (0-100)
            perf_score = self._calculate_performance_score(pricing)
            
            # Cost score (0-100, higher = cheaper)
            cost_score = self._calculate_cost_score(pricing)
            
            # Availability score (0 or 100)
            avail_score = 100.0 if model.get("has_pricing") else 0.0
            
            # Total weighted score
            total = (
                perf_score * perf_weight +
                cost_score * cost_weight +
                avail_score * avail_weight
            )
            
            # Generate reasoning
            reasoning = self._generate_reasoning(
                model_id, pricing, perf_score, cost_score, avail_score
            )
            
            scores.append(ModelScore(
                model_id=model_id,
                total_score=total,
                performance_score=perf_score,
                cost_score=cost_score,
                availability_score=avail_score,
                reasoning=reasoning,
            ))
        
        # Sort by total score
        scores.sort(key=lambda s: s.total_score, reverse=True)
        
        return scores
    
    def _calculate_performance_score(self, pricing: dict[str, Any]) -> float:
        """Calculate performance score based on tier and context window."""
        tier = pricing.get("tier", "unknown")
        context_window = pricing.get("context_window", 0)
        max_output = pricing.get("max_output_tokens", 0)
        
        # Tier scoring
        tier_scores = {
            "flagship": 100,
            "reasoning": 90,
            "premium": 70,
            "efficient": 60,
            "legacy": 30,
            "unknown": 0,
        }
        tier_score = tier_scores.get(tier, 0)
        
        # Context window bonus (normalize to 128k)
        context_bonus = min(context_window / 128000 * 20, 20)
        
        # Max output bonus (normalize to 16k)
        output_bonus = min(max_output / 16384 * 10, 10)
        
        return min(tier_score + context_bonus + output_bonus, 100.0)
    
    def _calculate_cost_score(self, pricing: dict[str, Any]) -> float:
        """Calculate cost score (higher = cheaper).
        
        We use total cost per 1M tokens (input + output assuming 1:1 ratio)
        """
        input_price = pricing.get("input_price_per_1m", 999.0)
        output_price = pricing.get("output_price_per_1m", 999.0)
        
        # Total cost (assuming equal input/output)
        total_cost = (input_price + output_price) / 2
        
        # Normalize to 0-100 (cheaper models get higher scores)
        # Assume max reasonable cost is $30 per 1M tokens
        max_cost = 30.0
        min_cost = 0.1
        
        # Inverse scoring: cheaper = higher score
        if total_cost >= max_cost:
            return 0.0
        elif total_cost <= min_cost:
            return 100.0
        else:
            # Linear inverse scale
            return 100.0 * (1 - (total_cost - min_cost) / (max_cost - min_cost))
    
    def _generate_reasoning(
        self,
        model_id: str,
        pricing: dict[str, Any],
        perf_score: float,
        cost_score: float,
        avail_score: float,
    ) -> str:
        """Generate human-readable reasoning for the score."""
        tier = pricing.get("tier", "unknown")
        description = pricing.get("description", "No description")
        input_price = pricing.get("input_price_per_1m", 0)
        output_price = pricing.get("output_price_per_1m", 0)
        
        parts = [
            f"Model: {model_id}",
            f"Tier: {tier}",
            f"Description: {description}",
            f"Performance score: {perf_score:.1f}/100",
            f"Cost score: {cost_score:.1f}/100 (${input_price:.2f}/${output_price:.2f} per 1M)",
            f"Availability: {avail_score:.0f}/100",
        ]
        
        return " | ".join(parts)
    
    def get_top_n_models(self, n: int = 5) -> list[ModelScore]:
        """Get top N models by score.
        
        Args:
            n: Number of top models to return
        
        Returns:
            List of ModelScore objects, sorted by score
        """
        if not self.model_scores:
            self.select_best_model()
        
        return self.model_scores[:n]
    
    def explain_selection(self) -> str:
        """Get detailed explanation of the selection process.
        
        Returns:
            Multi-line explanation string
        """
        if not self.best_model:
            return "No model selected yet. Call select_best_model() first."
        
        lines = [
            "=" * 70,
            "MODEL SELECTION REPORT",
            "=" * 70,
            f"Criteria: {self.criteria.value.upper()}",
            f"Total models evaluated: {len(self.model_scores)}",
            "",
            "TOP 5 MODELS:",
            "-" * 70,
        ]
        
        for i, score in enumerate(self.get_top_n_models(5), 1):
            lines.append(f"{i}. {score.model_id} (score: {score.total_score:.2f})")
            lines.append(f"   {score.reasoning}")
            lines.append("")
        
        lines.extend([
            "=" * 70,
            f"SELECTED: {self.best_model.model_id}",
            f"TOTAL SCORE: {self.best_model.total_score:.2f}/100",
            "=" * 70,
        ])
        
        return "\n".join(lines)
