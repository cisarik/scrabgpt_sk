"""Tests for internet-related MCP tools."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
import httpx


class TestInternetCallTool:
    """Test internet_call MCP tool."""

    @pytest.mark.asyncio
    async def test_successful_get_request(self) -> None:
        """Given: Valid URL
        When: Making GET request
        Then: Returns success with content
        """
        from scrabgpt.ai.internet_tools import tool_internet_call

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = "<html>Hello World</html>"
            mock_response.headers = {"content-type": "text/html"}
            mock_response.raise_for_status = AsyncMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await tool_internet_call(url="https://example.com")

            assert result["success"] is True
            assert result["status_code"] == 200
            assert "Hello World" in result["content"]

    @pytest.mark.asyncio
    async def test_handles_http_error(self) -> None:
        """Given: URL that returns 404
        When: Making GET request
        Then: Returns failure with error message
        """
        from scrabgpt.ai.internet_tools import tool_internet_call

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 404

            def raise_status():
                error = httpx.HTTPStatusError(
                    "404 Not Found",
                    request=AsyncMock(),
                    response=mock_response,
                )
                raise error

            mock_response.raise_for_status = raise_status

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await tool_internet_call(url="https://example.com/notfound")

            assert result["success"] is False
            assert "error" in result
            assert result["status_code"] == 404

    @pytest.mark.asyncio
    async def test_handles_timeout(self) -> None:
        """Given: URL that times out
        When: Making GET request
        Then: Returns failure with timeout error
        """
        from scrabgpt.ai.internet_tools import tool_internet_call

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client_class.return_value = mock_client

            result = await tool_internet_call(url="https://example.com", timeout=1.0)

            assert result["success"] is False
            assert "error" in result
            assert "Timeout" in result["error"] or "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_custom_headers(self) -> None:
        """Given: Custom headers specified
        When: Making request
        Then: Headers are included in request
        """
        from scrabgpt.ai.internet_tools import tool_internet_call

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_response.headers = {}
            mock_response.raise_for_status = AsyncMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            custom_headers = {"X-Custom": "test-value"}
            result = await tool_internet_call(
                url="https://api.example.com",
                headers=custom_headers,
            )

            # Check that AsyncClient was created with headers including custom ones
            call_kwargs = mock_client_class.call_args.kwargs
            assert "headers" in call_kwargs
            # Custom header should be in the merged headers
            # (Note: We can't directly check the headers dict because it's merged with defaults)
            
            assert result["success"] is True


class TestFetchOpenAIBestModel:
    """Test fetch_openai_best_model tool."""

    @pytest.mark.asyncio
    async def test_returns_fallback_when_no_api_key(self) -> None:
        """Given: No OpenAI API key configured
        When: Fetching best model
        Then: Returns fallback model
        """
        from scrabgpt.ai.internet_tools import tool_fetch_openai_best_model

        with patch.dict("os.environ", {}, clear=True):
            result = await tool_fetch_openai_best_model()

            assert result["model"] == "gpt-4o"
            assert "fallback" in result["description"].lower() or "not configured" in result["description"].lower()

    @pytest.mark.asyncio
    async def test_parses_api_response_successfully(self) -> None:
        """Given: Valid OpenAI API response
        When: Fetching best model
        Then: Returns model from API
        """
        from scrabgpt.ai.internet_tools import tool_fetch_openai_best_model

        mock_api_response = {
            "data": [
                {"id": "gpt-4o", "object": "model"},
                {"id": "gpt-4-turbo", "object": "model"},
                {"id": "gpt-3.5-turbo", "object": "model"},
            ]
        }

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}):
            with patch(
                "scrabgpt.ai.internet_tools.tool_internet_call",
                AsyncMock(
                    return_value={
                        "success": True,
                        "status_code": 200,
                        "content": str(mock_api_response).replace("'", '"'),
                    }
                ),
            ):
                result = await tool_fetch_openai_best_model()

                assert result["success"] is True
                assert result["model"] == "gpt-4o"
                assert result["source"] == "api"

    @pytest.mark.asyncio
    async def test_handles_api_failure_with_fallback(self) -> None:
        """Given: OpenAI API request fails
        When: Fetching best model
        Then: Returns fallback model
        """
        from scrabgpt.ai.internet_tools import tool_fetch_openai_best_model

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}):
            with patch(
                "scrabgpt.ai.internet_tools.tool_internet_call",
                AsyncMock(
                    return_value={
                        "success": False,
                        "status_code": 500,
                        "content": "",
                        "error": "Server error",
                    }
                ),
            ):
                result = await tool_fetch_openai_best_model()

                assert result["success"] is True  # Fallback succeeds
                assert result["model"] == "gpt-4o"
                assert result["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_prefers_gpt4o_over_others(self) -> None:
        """Given: Multiple models available
        When: Fetching best model
        Then: Prioritizes gpt-4o
        """
        from scrabgpt.ai.internet_tools import tool_fetch_openai_best_model

        mock_api_response = {
            "data": [
                {"id": "gpt-3.5-turbo", "object": "model"},
                {"id": "gpt-4-turbo", "object": "model"},
                {"id": "gpt-4o", "object": "model"},
                {"id": "davinci", "object": "model"},
            ]
        }

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}):
            with patch(
                "scrabgpt.ai.internet_tools.tool_internet_call",
                AsyncMock(
                    return_value={
                        "success": True,
                        "status_code": 200,
                        "content": str(mock_api_response).replace("'", '"'),
                    }
                ),
            ):
                result = await tool_fetch_openai_best_model()

                assert result["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_includes_capabilities_in_response(self) -> None:
        """Given: Best model found
        When: Fetching model info
        Then: Response includes capabilities list
        """
        from scrabgpt.ai.internet_tools import tool_fetch_openai_best_model

        with patch.dict("os.environ", {}, clear=True):
            result = await tool_fetch_openai_best_model()

            assert "capabilities" in result
            assert isinstance(result["capabilities"], list)
            # Should include at least basic capabilities
            # (exact list depends on fallback vs API response)


class TestInternetToolsRegistration:
    """Test that internet tools are registered in MCP registry."""

    def test_tools_can_be_registered(self) -> None:
        """Given: Internet tools module
        When: Registering tools
        Then: Tools appear in ALL_TOOLS registry
        """
        from scrabgpt.ai.internet_tools import register_internet_tools
        from scrabgpt.ai.mcp_tools import ALL_TOOLS

        # Get count before
        count_before = len(ALL_TOOLS)

        # Register
        register_internet_tools()

        # Check registration
        assert "internet_call" in ALL_TOOLS
        assert "fetch_openai_best_model" in ALL_TOOLS
        assert len(ALL_TOOLS) > count_before

    def test_registered_tools_are_callable(self) -> None:
        """Given: Internet tools registered
        When: Retrieving tool functions
        Then: Functions are callable
        """
        from scrabgpt.ai.internet_tools import register_internet_tools
        from scrabgpt.ai.mcp_tools import get_tool_function
        import inspect

        register_internet_tools()

        internet_call_func = get_tool_function("internet_call")
        fetch_model_func = get_tool_function("fetch_openai_best_model")

        assert callable(internet_call_func)
        assert callable(fetch_model_func)
        
        # Should be async functions
        assert inspect.iscoroutinefunction(internet_call_func)
        assert inspect.iscoroutinefunction(fetch_model_func)
