"""Compatibility-free adapter for converting internal tools to Vertex AI tools."""

from __future__ import annotations

from .mcp_adapter import execute_tool, get_gemini_tools

__all__ = ["get_gemini_tools", "execute_tool"]
