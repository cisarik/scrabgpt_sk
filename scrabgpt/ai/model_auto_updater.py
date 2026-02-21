"""Automatic model updater for OpenAI best model.

This module updates OPENAI_MODELS (primary model = first item)
based on the model selector agent's recommendations.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .model_selector_agent import ModelSelectorAgent, SelectionCriteria
from .model_fetcher import ModelFetchError

log = logging.getLogger("scrabgpt.ai.model_auto_updater")


def is_auto_update_enabled() -> bool:
    """Check if auto-update is enabled in environment.
    
    Returns:
        True if OPENAI_BEST_MODEL_AUTO_UPDATE is "true"
    """
    value = os.getenv("OPENAI_BEST_MODEL_AUTO_UPDATE", "false").lower()
    return value in ("true", "1", "yes", "on")


def get_current_model() -> str:
    """Get current primary OpenAI model from environment.
    
    Returns:
        Current model ID or "gpt-5.2" as default
    """
    raw_models = os.getenv("OPENAI_MODELS", "")
    for item in raw_models.split(","):
        model_id = item.strip()
        if model_id:
            return model_id
    return "gpt-5.2"


def update_env_file(model_id: str, env_path: Path | None = None) -> bool:
    """Update OPENAI_MODELS in .env file.
    
    Args:
        model_id: New model ID to set
        env_path: Path to .env file (auto-detected if None)
    
    Returns:
        True if update successful
    """
    if env_path is None:
        # Find .env in project root
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent
        env_path = project_root / ".env"
    
    if not env_path.exists():
        log.warning(".env file not found at %s", env_path)
        return False
    
    try:
        # Read current .env content
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Find and update OPENAI_MODELS line
        updated_openai_models = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("OPENAI_MODELS="):
                lines[i] = f"OPENAI_MODELS='{model_id}'\n"
                updated_openai_models = True
                log.info("Updated OPENAI_MODELS to '%s' in .env", model_id)

        # If OPENAI_MODELS key not found, append it
        if not updated_openai_models:
            lines.append(f"\nOPENAI_MODELS='{model_id}'\n")
            log.info("Added OPENAI_MODELS='%s' to .env", model_id)
        
        # Write back
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        
        # Update current environment (doesn't affect running process, only for next load)
        os.environ["OPENAI_MODELS"] = model_id
        
        return True
    
    except Exception as e:
        log.exception("Failed to update .env file: %s", e)
        return False


def check_and_update_model(
    api_key: str | None = None,
    criteria: SelectionCriteria = SelectionCriteria.BALANCED,
    force: bool = False,
) -> dict[str, Any]:
    """Check for best model and update if needed.
    
    Args:
        api_key: OpenAI API key
        criteria: Selection criteria
        force: Force update even if auto-update disabled
    
    Returns:
        Dict with:
        - updated: bool (whether update was performed)
        - current_model: str (current model before check)
        - recommended_model: str (recommended model from agent)
        - changed: bool (whether model changed)
        - error: str | None (error message if failed)
    """
    current_model = get_current_model()
    
    result = {
        "updated": False,
        "current_model": current_model,
        "recommended_model": current_model,
        "changed": False,
        "error": None,
    }
    
    # Check if auto-update is enabled (or forced)
    if not force and not is_auto_update_enabled():
        result["error"] = "Auto-update disabled (OPENAI_BEST_MODEL_AUTO_UPDATE=false)"
        log.debug("Auto-update disabled, skipping")
        return result
    
    try:
        # Use agent to find best model
        agent = ModelSelectorAgent(
            api_key=api_key,
            criteria=criteria,
            exclude_preview=True,
            exclude_legacy=True,
        )
        
        best = agent.select_best_model()
        recommended_model = best.model_id
        
        result["recommended_model"] = recommended_model
        
        # Check if model changed
        if recommended_model != current_model:
            result["changed"] = True
            
            # Update .env file
            if update_env_file(recommended_model):
                result["updated"] = True
                log.info(
                    "Model updated: %s -> %s (score: %.2f)",
                    current_model,
                    recommended_model,
                    best.total_score
                )
            else:
                result["error"] = "Failed to write to .env file"
        else:
            log.info("Current model %s is still the best", current_model)
    
    except ModelFetchError as e:
        result["error"] = str(e)
        log.exception("Failed to check for best model")
    except Exception as e:
        result["error"] = f"Unexpected error: {e}"
        log.exception("Unexpected error during model update")
    
    return result


def run_auto_update_check() -> None:
    """Run automatic model update check.
    
    This is the main entry point for scheduled/startup checks.
    """
    if not is_auto_update_enabled():
        log.debug("Auto-update disabled, skipping scheduled check")
        return
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log.warning("OPENAI_API_KEY not set, cannot run auto-update")
        return
    
    log.info("Running automatic model update check...")
    
    result = check_and_update_model(
        api_key=api_key,
        criteria=SelectionCriteria.BALANCED,
        force=False,
    )
    
    if result["error"]:
        log.error("Auto-update failed: %s", result["error"])
    elif result["updated"]:
        log.info("Auto-update successful: %s -> %s", 
                 result["current_model"], 
                 result["recommended_model"])
    else:
        log.info("Auto-update check complete, no changes needed")
