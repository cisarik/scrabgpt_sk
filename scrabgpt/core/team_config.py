"""Team configuration management for multi-model providers.

A "Team" is a saved configuration of models from a specific provider
(OpenRouter, Novita, etc.) that compete against each other.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("scrabgpt.core.team_config")

# Default location for team configurations
DEFAULT_TEAMS_DIR = Path.home() / ".scrabgpt" / "teams"
DEFAULT_CONFIG_FILE = Path.home() / ".scrabgpt" / "config.json"


@dataclass
class TeamConfig:
    """Configuration for a team of models from a provider."""
    
    name: str
    provider: str  # "openrouter", "novita", etc.
    model_ids: list[str]  # Just model IDs, e.g. ["deepseek/deepseek-r1-0528"]
    timeout_seconds: int = 120
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "provider": self.provider,
            "model_ids": self.model_ids,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TeamConfig:
        """Create from dictionary loaded from JSON."""
        # Support both new format (model_ids) and old format (models)
        model_ids = data.get("model_ids", [])
        if not model_ids and "models" in data:
            # Migrate old format: extract IDs from model objects
            model_ids = [m.get("id", "") for m in data.get("models", []) if m.get("id")]
        
        return cls(
            name=data["name"],
            provider=data["provider"],
            model_ids=model_ids,
            timeout_seconds=data.get("timeout_seconds", 120),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )


class TeamManager:
    """Manages saving and loading team configurations."""
    
    def __init__(self, teams_dir: Path | None = None, config_file: Path | None = None):
        """Initialize team manager.
        
        Args:
            teams_dir: Directory to store team configs (default: ~/.scrabgpt/teams)
            config_file: Path to config file (default: ~/.scrabgpt/config.json)
        """
        self.teams_dir = teams_dir or DEFAULT_TEAMS_DIR
        self.teams_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = config_file or DEFAULT_CONFIG_FILE
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        log.info("Team manager initialized: %s", self.teams_dir)
    
    def get_team_path(self, provider: str, team_name: str | None = None) -> Path:
        """Get path to team config file for a provider.
        
        Args:
            provider: Provider name (e.g., "openrouter", "novita")
            team_name: Optional team name. If None, returns default team path.
        
        Returns:
            Path to team config JSON file
        """
        if team_name:
            # Sanitize team name for filename
            safe_name = team_name.lower().replace(" ", "_").replace("/", "_")
            return self.teams_dir / f"{provider}_{safe_name}.json"
        return self.teams_dir / f"{provider}_team.json"
    
    def save_team(self, team: TeamConfig) -> None:
        """Save team configuration to disk.
        
        Args:
            team: Team configuration to save
        """
        team.updated_at = datetime.now().isoformat()
        path = self.get_team_path(team.provider, team.name)
        
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(team.to_dict(), f, indent=2, ensure_ascii=False)
            log.info(
                "Saved team '%s' for %s: %d models",
                team.name,
                team.provider,
                len(team.model_ids),
            )
        except Exception as e:
            log.error("Failed to save team '%s' for %s: %s", team.name, team.provider, e)
            raise
    
    def load_team(self, provider: str) -> TeamConfig | None:
        """Load team configuration for a provider.
        
        Args:
            provider: Provider name (e.g., "openrouter", "novita")
        
        Returns:
            TeamConfig if exists, None otherwise
        """
        path = self.get_team_path(provider)
        
        if not path.exists():
            log.debug("No saved team found for %s", provider)
            return None
        
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            team = TeamConfig.from_dict(data)
            log.info(
                "Loaded team '%s' for %s: %d models",
                team.name,
                team.provider,
                len(team.model_ids),
            )
            return team
        except Exception as e:
            log.error("Failed to load team for %s: %s", provider, e)
            return None
    
    def delete_team(self, provider: str) -> None:
        """Delete team configuration for a provider.
        
        Args:
            provider: Provider name
        """
        path = self.get_team_path(provider)
        
        if path.exists():
            try:
                path.unlink()
                log.info("Deleted team for %s", provider)
            except Exception as e:
                log.error("Failed to delete team for %s: %s", provider, e)
                raise
    
    def list_teams(self, provider: str | None = None) -> list[TeamConfig]:
        """List all saved team configurations.
        
        Args:
            provider: Optional provider filter (e.g., "novita", "openrouter")
        
        Returns:
            List of all saved teams (optionally filtered by provider)
        """
        teams = []
        
        # Match pattern: provider_*.json or *_team.json
        if provider:
            pattern = f"{provider}_*.json"
        else:
            pattern = "*.json"
        
        for path in self.teams_dir.glob(pattern):
            # Skip config.json if it's in teams dir
            if path.name == "config.json":
                continue
                
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                team = TeamConfig.from_dict(data)
                
                # Filter by provider if specified
                if provider is None or team.provider == provider:
                    teams.append(team)
            except Exception as e:
                log.warning("Failed to load team from %s: %s", path, e)
        
        return teams
    
    def save_provider_models(
        self,
        provider: str,
        models: list[dict[str, Any]],
        timeout_seconds: int = 120,
    ) -> TeamConfig:
        """Save models for a provider (convenience method).
        
        Args:
            provider: Provider name
            models: List of model configurations (IDs will be extracted)
            timeout_seconds: Timeout for API calls
        
        Returns:
            Created/updated TeamConfig
        """
        # Extract model IDs from full model objects
        model_ids = [m.get("id", "") for m in models if m.get("id")]
        
        # Try to load existing team to preserve name and created_at
        existing = self.load_team(provider)
        
        if existing:
            team = TeamConfig(
                name=existing.name,
                provider=provider,
                model_ids=model_ids,
                timeout_seconds=timeout_seconds,
                created_at=existing.created_at,
            )
        else:
            # Create new team with default name
            team = TeamConfig(
                name=f"{provider.title()} Team",
                provider=provider,
                model_ids=model_ids,
                timeout_seconds=timeout_seconds,
            )
        
        self.save_team(team)
        return team
    
    def load_provider_models(
        self,
        provider: str,
    ) -> tuple[list[str], int] | None:
        """Load model IDs for a provider (convenience method).
        
        Args:
            provider: Provider name
        
        Returns:
            Tuple of (model_ids list, timeout_seconds) if exists, None otherwise
        """
        team = self.load_team(provider)
        
        if team:
            return (team.model_ids, team.timeout_seconds)
        
        return None
    
    def save_opponent_mode(self, mode: str) -> None:
        """Save current opponent mode to config.
        
        Args:
            mode: Opponent mode value (e.g., "novita", "openrouter", "best_model")
        """
        try:
            # Load existing config or create new
            config = {}
            if self.config_file.exists():
                with self.config_file.open("r", encoding="utf-8") as f:
                    config = json.load(f)
            
            # Update opponent mode
            config["opponent_mode"] = mode
            
            # Save back
            with self.config_file.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            log.info("Saved opponent mode: %s", mode)
        except Exception as e:
            log.error("Failed to save opponent mode: %s", e)
    
    def load_opponent_mode(self) -> str | None:
        """Load saved opponent mode from config.
        
        Returns:
            Opponent mode string if exists, None otherwise
        """
        try:
            if not self.config_file.exists():
                return None
            
            with self.config_file.open("r", encoding="utf-8") as f:
                config = json.load(f)
            
            mode = config.get("opponent_mode")
            if mode:
                log.info("Loaded opponent mode: %s", mode)
                return str(mode) if mode else None
            return None
        except Exception as e:
            log.error("Failed to load opponent mode: %s", e)
            return None
    
    def save_active_team(self, provider: str, team_name: str) -> None:
        """Save which team is active for a provider.
        
        Args:
            provider: Provider name
            team_name: Team name to set as active
        """
        try:
            config = {}
            if self.config_file.exists():
                with self.config_file.open("r", encoding="utf-8") as f:
                    config = json.load(f)
            
            if "active_teams" not in config:
                config["active_teams"] = {}
            
            config["active_teams"][provider] = team_name
            
            with self.config_file.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            log.info("Saved active team for %s: %s", provider, team_name)
        except Exception as e:
            log.error("Failed to save active team for %s: %s", provider, e)
    
    def load_active_team(self, provider: str) -> str | None:
        """Load which team is active for a provider.
        
        Args:
            provider: Provider name
        
        Returns:
            Active team name if set, None otherwise
        """
        try:
            if not self.config_file.exists():
                return None
            
            with self.config_file.open("r", encoding="utf-8") as f:
                config = json.load(f)
            
            active_teams = config.get("active_teams", {})
            team_name = active_teams.get(provider)
            
            if team_name:
                log.info("Loaded active team for %s: %s", provider, team_name)
                return str(team_name) if team_name else None
            return None
        except Exception as e:
            log.error("Failed to load active team for %s: %s", provider, e)
            return None
    
    def load_active_team_config(self, provider: str) -> TeamConfig | None:
        """Load the active team configuration for a provider.
        
        Args:
            provider: Provider name
        
        Returns:
            Active TeamConfig if exists, None otherwise
        """
        team_name = self.load_active_team(provider)
        if not team_name:
            # Fall back to default team if no active team set
            return self.load_team(provider)
        
        # Load the specific named team
        path = self.get_team_path(provider, team_name)
        if not path.exists():
            log.warning("Active team file not found: %s", path)
            return self.load_team(provider)  # Fall back to default
        
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return TeamConfig.from_dict(data)
        except Exception as e:
            log.error("Failed to load active team: %s", e)
            return None


# Global instance
_team_manager: TeamManager | None = None


def get_team_manager() -> TeamManager:
    """Get global team manager instance (lazy init)."""
    global _team_manager
    
    if _team_manager is None:
        _team_manager = TeamManager()
    
    return _team_manager
