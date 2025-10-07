"""OpenAI model information fetcher.

This module provides tools for fetching OpenAI model information including:
- Available models
- Pricing information
- Capabilities and context limits
"""

from __future__ import annotations

import logging
from typing import Any
from datetime import datetime, timedelta

import httpx
from openai import OpenAI

log = logging.getLogger("scrabgpt.ai.model_fetcher")


# Cache for model data (avoid excessive API calls)
_model_cache: dict[str, Any] = {}
_cache_timestamp: datetime | None = None
_cache_ttl = timedelta(hours=1)  # Cache for 1 hour


class ModelFetchError(Exception):
    """Raised when model fetching fails."""
    pass


def fetch_openai_models(api_key: str | None = None, use_cache: bool = True) -> list[dict[str, Any]]:
    """Fetch all available OpenAI models.
    
    Args:
        api_key: OpenAI API key (uses env var if None)
        use_cache: Whether to use cached data
    
    Returns:
        List of model dicts with keys: id, created, owned_by, etc.
    
    Raises:
        ModelFetchError: If fetching fails
    """
    global _model_cache, _cache_timestamp
    
    # Check cache
    if use_cache and _cache_timestamp:
        if datetime.now() - _cache_timestamp < _cache_ttl:
            cached_models = _model_cache.get("models")
            if cached_models:
                log.debug("Using cached OpenAI models (%d models)", len(cached_models))
                return cached_models
    
    try:
        client = OpenAI(api_key=api_key)
        
        # Fetch models
        response = client.models.list()
        models = [model.dict() for model in response.data]
        
        # Filter for text generation models (exclude embeddings, TTS, etc.)
        text_models = [
            m for m in models
            if any(keyword in m["id"].lower() for keyword in ["gpt", "o1", "text"])
            and not any(keyword in m["id"].lower() for keyword in ["embed", "tts", "whisper", "dall-e"])
        ]
        
        # Update cache
        _model_cache["models"] = text_models
        _cache_timestamp = datetime.now()
        
        log.info("Fetched %d OpenAI text generation models", len(text_models))
        return text_models
    
    except Exception as e:
        log.exception("Failed to fetch OpenAI models")
        raise ModelFetchError(f"Failed to fetch OpenAI models: {e}") from e


def fetch_model_pricing() -> dict[str, dict[str, Any]]:
    """Fetch OpenAI model pricing information.
    
    Note: OpenAI doesn't provide a pricing API, so we hardcode known pricing.
    This should be updated periodically from https://openai.com/pricing
    
    Returns:
        Dict mapping model_id to pricing info:
        {
            "gpt-4o": {
                "input_price_per_1m": 2.50,
                "output_price_per_1m": 10.00,
                "context_window": 128000,
                "max_output_tokens": 16384
            }
        }
    """
    # Pricing as of January 2024
    # Source: https://openai.com/pricing
    return {
        # GPT-4o models (latest, most capable)
        "gpt-4o": {
            "input_price_per_1m": 2.50,
            "output_price_per_1m": 10.00,
            "context_window": 128000,
            "max_output_tokens": 16384,
            "tier": "flagship",
            "description": "Most capable model, multimodal"
        },
        "gpt-4o-mini": {
            "input_price_per_1m": 0.15,
            "output_price_per_1m": 0.60,
            "context_window": 128000,
            "max_output_tokens": 16384,
            "tier": "efficient",
            "description": "Affordable and intelligent small model"
        },
        "gpt-4o-2024-11-20": {
            "input_price_per_1m": 2.50,
            "output_price_per_1m": 10.00,
            "context_window": 128000,
            "max_output_tokens": 16384,
            "tier": "flagship",
            "description": "Latest GPT-4o snapshot"
        },
        "gpt-4o-2024-08-06": {
            "input_price_per_1m": 2.50,
            "output_price_per_1m": 10.00,
            "context_window": 128000,
            "max_output_tokens": 16384,
            "tier": "flagship",
            "description": "GPT-4o August snapshot with structured outputs"
        },
        
        # GPT-4 Turbo models
        "gpt-4-turbo": {
            "input_price_per_1m": 10.00,
            "output_price_per_1m": 30.00,
            "context_window": 128000,
            "max_output_tokens": 4096,
            "tier": "premium",
            "description": "Previous generation flagship"
        },
        "gpt-4-turbo-preview": {
            "input_price_per_1m": 10.00,
            "output_price_per_1m": 30.00,
            "context_window": 128000,
            "max_output_tokens": 4096,
            "tier": "premium",
            "description": "GPT-4 Turbo preview"
        },
        
        # GPT-3.5 models
        "gpt-3.5-turbo": {
            "input_price_per_1m": 0.50,
            "output_price_per_1m": 1.50,
            "context_window": 16385,
            "max_output_tokens": 4096,
            "tier": "legacy",
            "description": "Fast, affordable legacy model"
        },
        
        # o1 models (reasoning)
        "o1-preview": {
            "input_price_per_1m": 15.00,
            "output_price_per_1m": 60.00,
            "context_window": 128000,
            "max_output_tokens": 32768,
            "tier": "reasoning",
            "description": "Advanced reasoning model (preview)"
        },
        "o1-mini": {
            "input_price_per_1m": 3.00,
            "output_price_per_1m": 12.00,
            "context_window": 128000,
            "max_output_tokens": 65536,
            "tier": "reasoning",
            "description": "Faster reasoning model"
        },
    }


def enrich_models_with_pricing(
    models: list[dict[str, Any]],
    pricing: dict[str, dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Enrich model data with pricing information.
    
    Args:
        models: List of models from OpenAI API
        pricing: Pricing dict (fetches default if None)
    
    Returns:
        List of enriched model dicts
    """
    if pricing is None:
        pricing = fetch_model_pricing()
    
    enriched = []
    
    for model in models:
        model_id = model["id"]
        enriched_model = model.copy()
        
        # Try exact match first
        if model_id in pricing:
            enriched_model["pricing"] = pricing[model_id]
        else:
            # Try prefix match (e.g., "gpt-4o-2024-05-13" matches "gpt-4o")
            for price_key, price_data in pricing.items():
                if model_id.startswith(price_key):
                    enriched_model["pricing"] = price_data.copy()
                    enriched_model["pricing"]["note"] = f"Pricing inherited from {price_key}"
                    break
        
        # Add flag for whether we have pricing
        enriched_model["has_pricing"] = "pricing" in enriched_model
        
        enriched.append(enriched_model)
    
    return enriched


def get_model_info(model_id: str, api_key: str | None = None) -> dict[str, Any]:
    """Get detailed information about a specific model.
    
    Args:
        model_id: Model ID (e.g., "gpt-4o")
        api_key: OpenAI API key
    
    Returns:
        Dict with model info including pricing
    
    Raises:
        ModelFetchError: If model not found
    """
    models = fetch_openai_models(api_key)
    pricing = fetch_model_pricing()
    enriched = enrich_models_with_pricing(models, pricing)
    
    for model in enriched:
        if model["id"] == model_id:
            return model
    
    raise ModelFetchError(f"Model not found: {model_id}")


def clear_cache() -> None:
    """Clear the model cache."""
    global _model_cache, _cache_timestamp
    _model_cache = {}
    _cache_timestamp = None
    log.debug("Model cache cleared")
