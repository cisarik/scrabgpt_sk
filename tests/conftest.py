"""Pytest configuration and fixtures.

This file is automatically loaded by pytest and provides:
- Environment variable loading from .env
- Shared fixtures for all tests
- Custom markers configuration
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
import pytest


# Load .env file at the start of test session
def pytest_configure(config):
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✓ Loaded environment from {env_file}")
    else:
        print(f"⚠ No .env file found at {env_file}")
    
    # Check for API keys
    if os.getenv("OPENAI_API_KEY"):
        print("✓ OPENAI_API_KEY found")
    else:
        print("⚠ OPENAI_API_KEY not set (tests marked @pytest.mark.openai will fail)")
    
    if os.getenv("OPENROUTER_API_KEY"):
        print("✓ OPENROUTER_API_KEY found")
    else:
        print("⚠ OPENROUTER_API_KEY not set (tests marked @pytest.mark.openrouter will fail)")


@pytest.fixture
def openai_api_key() -> str | None:
    """Get OpenAI API key from environment.
    
    Returns:
        API key or None if not set
    """
    return os.getenv("OPENAI_API_KEY")


@pytest.fixture
def openrouter_api_key() -> str | None:
    """Get OpenRouter API key from environment.
    
    Returns:
        API key or None if not set
    """
    return os.getenv("OPENROUTER_API_KEY")


def pytest_collection_modifyitems(config, items):
    """Auto-mark tests based on markers.
    
    - Tests with @pytest.mark.openai or @pytest.mark.openrouter are also marked as @pytest.mark.internet
    - Tests with @pytest.mark.network are also marked as @pytest.mark.internet
    """
    for item in items:
        # Auto-add internet marker to API tests
        if "openai" in item.keywords or "openrouter" in item.keywords or "network" in item.keywords:
            item.add_marker(pytest.mark.internet)
