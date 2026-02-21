"""Compatibility-free adapter for converting internal tools to provider tool formats."""

from __future__ import annotations

from .mcp_adapter import execute_tool, get_gemini_tools, get_openai_tools

__all__ = ["get_gemini_tools", "get_openai_tools", "execute_tool"]
