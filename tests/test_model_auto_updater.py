"""Tests for model auto-updater."""

from __future__ import annotations

import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile

from scrabgpt.ai.model_auto_updater import (
    is_auto_update_enabled,
    get_current_model,
    update_env_file,
    check_and_update_model,
)
from scrabgpt.ai.model_selector_agent import SelectionCriteria


class TestAutoUpdateConfig:
    """Test configuration helpers."""
    
    def test_is_auto_update_enabled_true(self, monkeypatch):
        """Given: OPENAI_BEST_MODEL_AUTO_UPDATE=true
        When: Checking if enabled
        Then: Returns True
        """
        monkeypatch.setenv("OPENAI_BEST_MODEL_AUTO_UPDATE", "true")
        assert is_auto_update_enabled() is True
        
        # Test variations
        monkeypatch.setenv("OPENAI_BEST_MODEL_AUTO_UPDATE", "True")
        assert is_auto_update_enabled() is True
        
        monkeypatch.setenv("OPENAI_BEST_MODEL_AUTO_UPDATE", "1")
        assert is_auto_update_enabled() is True
    
    def test_is_auto_update_enabled_false(self, monkeypatch):
        """Given: OPENAI_BEST_MODEL_AUTO_UPDATE=false
        When: Checking if enabled
        Then: Returns False
        """
        monkeypatch.setenv("OPENAI_BEST_MODEL_AUTO_UPDATE", "false")
        assert is_auto_update_enabled() is False
        
        monkeypatch.setenv("OPENAI_BEST_MODEL_AUTO_UPDATE", "0")
        assert is_auto_update_enabled() is False
    
    def test_get_current_model_from_env(self, monkeypatch):
        """Given: OPENAI_PLAYER_MODEL set in environment
        When: Getting current model
        Then: Returns model from environment
        """
        monkeypatch.setenv("OPENAI_PLAYER_MODEL", "gpt-4o")
        assert get_current_model() == "gpt-4o"
    
    def test_get_current_model_default(self, monkeypatch):
        """Given: OPENAI_PLAYER_MODEL not set
        When: Getting current model
        Then: Returns default model
        """
        monkeypatch.delenv("OPENAI_PLAYER_MODEL", raising=False)
        assert get_current_model() == "gpt-4o-mini"


class TestEnvFileUpdate:
    """Test .env file updates."""
    
    def test_update_env_file_creates_if_missing(self):
        """Given: Temporary .env file
        When: Updating model
        Then: File is updated correctly
        """
        with NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("OPENAI_API_KEY='test-key'\n")
            f.write("OPENAI_PLAYER_MODEL='gpt-3.5-turbo'\n")
            env_path = Path(f.name)
        
        try:
            # Update model
            result = update_env_file("gpt-4o", env_path)
            assert result is True
            
            # Verify content
            content = env_path.read_text()
            assert "OPENAI_PLAYER_MODEL='gpt-4o'" in content
            assert "gpt-3.5-turbo" not in content
        finally:
            env_path.unlink()
    
    def test_update_env_file_appends_if_not_present(self):
        """Given: .env file without OPENAI_PLAYER_MODEL
        When: Updating model
        Then: Line is appended
        """
        with NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("OPENAI_API_KEY='test-key'\n")
            env_path = Path(f.name)
        
        try:
            # Update model
            result = update_env_file("gpt-4o", env_path)
            assert result is True
            
            # Verify content
            content = env_path.read_text()
            assert "OPENAI_PLAYER_MODEL='gpt-4o'" in content
        finally:
            env_path.unlink()
    
    def test_update_env_file_handles_missing_file(self):
        """Given: Non-existent .env file
        When: Updating model
        Then: Returns False without crashing
        """
        result = update_env_file("gpt-4o", Path("/nonexistent/path/.env"))
        assert result is False


class TestAutoUpdateWorkflow:
    """Test full auto-update workflow."""
    
    @pytest.mark.openai
    def test_check_and_update_when_disabled(self, openai_api_key, monkeypatch):
        """Given: Auto-update disabled
        When: Checking for updates
        Then: Returns without updating
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        monkeypatch.setenv("OPENAI_BEST_MODEL_AUTO_UPDATE", "false")
        monkeypatch.setenv("OPENAI_PLAYER_MODEL", "gpt-3.5-turbo")
        
        result = check_and_update_model(openai_api_key)
        
        assert result["updated"] is False
        assert result["error"] is not None
        assert "disabled" in result["error"].lower()
    
    @pytest.mark.openai
    def test_check_and_update_with_force(self, openai_api_key, monkeypatch):
        """Given: Auto-update disabled but force=True
        When: Checking for updates
        Then: Runs update check
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        monkeypatch.setenv("OPENAI_BEST_MODEL_AUTO_UPDATE", "false")
        monkeypatch.setenv("OPENAI_PLAYER_MODEL", "gpt-3.5-turbo")
        
        result = check_and_update_model(
            api_key=openai_api_key,
            force=True,
        )
        
        # Should have run the check (but might not update file in test env)
        assert "recommended_model" in result
        assert result["recommended_model"]  # Should have a recommendation
    
    @pytest.mark.openai
    @pytest.mark.stress
    def test_full_auto_update_workflow(self, openai_api_key, monkeypatch):
        """Stress test: Full auto-update workflow with temp .env file.
        
        This tests the complete workflow:
        1. Check current model
        2. Query OpenAI for available models
        3. Use agent to select best model
        4. Update .env file
        """
        if not openai_api_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        # Create temporary .env file
        with NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("OPENAI_API_KEY='test-key'\n")
            f.write("OPENAI_PLAYER_MODEL='gpt-3.5-turbo'\n")
            f.write("OPENAI_BEST_MODEL_AUTO_UPDATE='true'\n")
            env_path = Path(f.name)
        
        try:
            monkeypatch.setenv("OPENAI_PLAYER_MODEL", "gpt-3.5-turbo")
            monkeypatch.setenv("OPENAI_BEST_MODEL_AUTO_UPDATE", "true")
            
            # Run full workflow
            from scrabgpt.ai.model_auto_updater import check_and_update_model
            
            result = check_and_update_model(
                api_key=openai_api_key,
                criteria=SelectionCriteria.COST,  # Use cost criteria for test
                force=True,
            )
            
            print("\nAuto-update result:")
            print(f"  Current: {result['current_model']}")
            print(f"  Recommended: {result['recommended_model']}")
            print(f"  Changed: {result['changed']}")
            print(f"  Error: {result['error']}")
            
            # Verify result structure
            assert "current_model" in result
            assert "recommended_model" in result
            assert "changed" in result
            
            # With COST criteria, should recommend affordable model
            if result["recommended_model"]:
                assert "mini" in result["recommended_model"].lower() or \
                       result["current_model"] == result["recommended_model"]
        
        finally:
            env_path.unlink()
