"""Opponent mode enumeration and configuration."""

from __future__ import annotations

from enum import Enum


class OpponentMode(Enum):
    """AI opponent mode selection.
    
    Determines how the AI opponent generates moves:
    - LMSTUDIO: Local OpenAI-compatible endpoint (LMStudio/localhost)
    - BEST_MODEL: Parallel OpenAI model competition (from OPENAI_MODELS)
    - OPENROUTER: Multi-model competition via OpenRouter
    - NOVITA: Multi-model competition via Novita (reasoning models)
    - GEMINI: Google Gemini model via Vertex AI (streaming + reasoning)
"""
    
    LMSTUDIO = "lmstudio"
    BEST_MODEL = "best_model"
    OPENROUTER = "openrouter"
    NOVITA = "novita"
    GEMINI = "gemini"
    
    @property
    def display_name_sk(self) -> str:
        """Slovak display name for UI."""
        names = {
            OpponentMode.LMSTUDIO: "LMStudio",
            OpponentMode.BEST_MODEL: "OpenAI",
            OpponentMode.OPENROUTER: "OpenRouter",
            OpponentMode.NOVITA: "Novita AI",
            OpponentMode.GEMINI: "Google",
        }
        return names[self]
    
    @property
    def description_sk(self) -> str:
        """Slovak description for UI."""
        descriptions = {
            OpponentMode.LMSTUDIO: (
                "Lokálny OpenAI-compatible endpoint (napr. LMStudio) s rovnakým "
                "agentickým flow ako ostatné režimy."
            ),
            OpponentMode.BEST_MODEL: (
                "Paralelné volanie vybraných OpenAI modelov. "
                "Použije sa najlepší legálny ťah podľa skóre."
            ),
            OpponentMode.OPENROUTER: "Paralelné volanie modelov ktoré vybraté na hru.",
            OpponentMode.NOVITA: "Paralelné volanie reasoning modelov (DeepSeek, Qwen, GLM, LLaMA).",
            OpponentMode.GEMINI: "Gemini model cez Google Vertex AI (reasoning + stream).",
        }
        return descriptions[self]
    
    @property
    def is_available(self) -> bool:
        """Whether this mode is currently available."""
        return True
    
    @classmethod
    def from_string(cls, mode: str) -> OpponentMode:
        """Convert string to OpponentMode.
        
        Args:
            mode: Mode string (e.g., "lmstudio", "best_model")
        
        Returns:
            OpponentMode enum value
        
        Raises:
            ValueError: If mode string is invalid
        """
        normalized = mode.lower().strip()
        legacy_map = {
            "agent": cls.LMSTUDIO,
            "offline": cls.LMSTUDIO,
            "llmstudio": cls.LMSTUDIO,
        }
        mapped = legacy_map.get(normalized)
        if mapped is not None:
            return mapped
        try:
            return cls(normalized)
        except ValueError:
            valid_modes = ", ".join([m.value for m in cls])
            raise ValueError(
                f"Invalid opponent mode: {mode}. Valid modes: {valid_modes}"
            )
