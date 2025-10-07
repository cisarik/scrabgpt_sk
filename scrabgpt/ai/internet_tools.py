"""Internet-related MCP tools for AI agents.

These tools allow agents to fetch information from the web.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("scrabgpt.ai.internet_tools")


async def tool_internet_call(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Make an HTTP request to a URL.
    
    Args:
        url: URL to request
        method: HTTP method (GET, POST, etc.)
        headers: Optional HTTP headers
        timeout: Request timeout in seconds
    
    Returns:
        {
            success: bool,
            status_code: int,
            content: str,
            error: str (if failed)
        }
    """
    try:
        default_headers = {
            "User-Agent": "ScrabGPT-Agent/1.0 (+https://github.com/cisarik/scrabgpt_sk)",
            "Accept": "text/html,application/json,*/*",
        }
        
        if headers:
            default_headers.update(headers)
        
        async with httpx.AsyncClient(
            http2=True,
            follow_redirects=True,
            timeout=timeout,
            headers=default_headers,
        ) as client:
            response = await client.request(method, url)
            response.raise_for_status()
            
            return {
                "success": True,
                "status_code": response.status_code,
                "content": response.text,
                "headers": dict(response.headers),
            }
    
    except httpx.HTTPError as e:
        log.warning("HTTP request failed for %s: %s", url, e)
        return {
            "success": False,
            "status_code": getattr(e.response, "status_code", 0) if hasattr(e, "response") else 0,
            "content": "",
            "error": f"HTTP error: {e}",
        }
    
    except Exception as e:
        log.exception("Unexpected error during HTTP request to %s: %s", url, e)
        return {
            "success": False,
            "status_code": 0,
            "content": "",
            "error": f"Request failed: {e}",
        }


async def tool_fetch_openai_best_model() -> dict[str, Any]:
    """Fetch information about the current best OpenAI model.
    
    This queries OpenAI's documentation/API to find the recommended
    flagship model for general use.
    
    Returns:
        {
            success: bool,
            model: str (e.g., "gpt-4o"),
            description: str,
            capabilities: list[str],
            error: str (if failed)
        }
    """
    try:
        # Strategy 1: Try OpenAI API /models endpoint
        api_url = "https://api.openai.com/v1/models"
        
        # Get API key from environment
        import os
        api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            return {
                "success": False,
                "model": "gpt-4o",  # Fallback
                "description": "OpenAI API key not configured",
                "capabilities": [],
                "error": "OPENAI_API_KEY not set in environment",
            }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        result = await tool_internet_call(
            url=api_url,
            method="GET",
            headers=headers,
            timeout=10.0,
        )
        
        if not result["success"]:
            # Fallback to hardcoded best model
            log.warning("Failed to fetch OpenAI models, using fallback")
            return {
                "success": True,
                "model": "gpt-4o",
                "description": "OpenAI's flagship multimodal model (fallback)",
                "capabilities": ["text", "vision", "function-calling", "json-mode"],
                "source": "fallback",
            }
        
        # Parse response
        import json
        try:
            data = json.loads(result["content"])
            models = data.get("data", [])
            
            # Find best model (prioritize gpt-4o, gpt-4-turbo)
            best_models = ["gpt-4o", "gpt-4-turbo", "gpt-4"]
            
            for preferred in best_models:
                for model_info in models:
                    model_id = model_info.get("id", "")
                    if model_id == preferred or model_id.startswith(preferred):
                        return {
                            "success": True,
                            "model": model_id,
                            "description": f"OpenAI's {model_id} model",
                            "capabilities": ["text", "function-calling", "json-mode"],
                            "source": "api",
                        }
            
            # If no preferred model found, return first one
            if models:
                first_model = models[0]["id"]
                return {
                    "success": True,
                    "model": first_model,
                    "description": f"OpenAI model: {first_model}",
                    "capabilities": ["text"],
                    "source": "api",
                }
            
        except json.JSONDecodeError as e:
            log.warning("Failed to parse OpenAI models response: %s", e)
        
        # Final fallback
        return {
            "success": True,
            "model": "gpt-4o",
            "description": "OpenAI's flagship multimodal model (fallback)",
            "capabilities": ["text", "vision", "function-calling", "json-mode"],
            "source": "fallback",
        }
    
    except Exception as e:
        log.exception("Error fetching best OpenAI model: %s", e)
        return {
            "success": False,
            "model": "gpt-4o",
            "description": "Error fetching model info",
            "capabilities": [],
            "error": str(e),
        }


# Register tools in main mcp_tools registry
def register_internet_tools() -> None:
    """Register internet tools in the main MCP tools registry."""
    from .mcp_tools import ALL_TOOLS
    
    ALL_TOOLS["internet_call"] = tool_internet_call
    ALL_TOOLS["fetch_openai_best_model"] = tool_fetch_openai_best_model
