"""Opponent mode enumeration and configuration."""

from __future__ import annotations

from enum import Enum


class OpponentMode(Enum):
    """AI opponent mode selection.
    
    Determines how the AI opponent generates moves:
    - AGENT: Uses MCP tools with configurable agent
    - BEST_MODEL: Uses OpenAI's best available model (auto-fetched)
    - OPENROUTER: Multi-model competition via OpenRouter
    - NOVITA: Multi-model competition via Novita (reasoning models)
    - OFFLINE: Local AI model (not implemented yet)
    """
    
    AGENT = "agent"
    BEST_MODEL = "best_model"
    OPENROUTER = "openrouter"
    NOVITA = "novita"
    OFFLINE = "offline"
    
    @property
    def display_name_sk(self) -> str:
        """Slovak display name for UI."""
        names = {
            OpponentMode.AGENT: "OpenAI Agent",
            OpponentMode.BEST_MODEL: "OpenAI API call",
            OpponentMode.OPENROUTER: "OpenRouter",
            OpponentMode.NOVITA: "Novita AI",
            OpponentMode.OFFLINE: "Offline AI",
        }
        return names[self]
    
    @property
    def description_sk(self) -> str:
        """Slovak description for UI."""
        descriptions = {
            OpponentMode.AGENT: "Hrať proti agentovi ktorý sa sám rozhoduje čo a kedy použije (aké nástroje=funkcie si podľa potreby zavolá) na to aby navrhol svoj ťah",
            OpponentMode.BEST_MODEL: "Hrať oproti najlepšiemu <GPT5> modelu",
            OpponentMode.OPENROUTER: "Paralelné volanie modelov ktoré vybraté na hru.",
            OpponentMode.NOVITA: "Paralelné volanie reasoning modelov (DeepSeek, Qwen, GLM, LLaMA).",
            OpponentMode.OFFLINE: "Hrať offline proti Vášmu PC",
        }
        return descriptions[self]
    
    @property
    def is_available(self) -> bool:
        """Whether this mode is currently available."""
        # OFFLINE not implemented yet
        if self == OpponentMode.OFFLINE:
            return False
        return True
    
    @classmethod
    def from_string(cls, mode: str) -> OpponentMode:
        """Convert string to OpponentMode.
        
        Args:
            mode: Mode string (e.g., "agent", "single")
        
        Returns:
            OpponentMode enum value
        
        Raises:
            ValueError: If mode string is invalid
        """
        try:
            return cls(mode.lower())
        except ValueError:
            valid_modes = ", ".join([m.value for m in cls])
            raise ValueError(
                f"Invalid opponent mode: {mode}. Valid modes: {valid_modes}"
            )
