from __future__ import annotations

import pytest

from scrabgpt.ai.openai_tools_client import OpenAIToolClient
from scrabgpt.ai.tool_adapter import get_openai_tools


class _DummyFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _DummyToolCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.id = call_id
        self.function = _DummyFunction(name, arguments)


class _DummyMessage:
    def __init__(self, content: str, tool_calls: list[_DummyToolCall] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class _DummyChoice:
    def __init__(self, message: _DummyMessage) -> None:
        self.message = message


class _DummyUsage:
    prompt_tokens = 11
    completion_tokens = 22


class _DummyResponse:
    def __init__(self, message: _DummyMessage) -> None:
        self.choices = [_DummyChoice(message)]
        self.usage = _DummyUsage()


class _DummyCompletions:
    def __init__(self) -> None:
        self.calls = 0
        self.requests: list[dict] = []

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.requests.append(kwargs)
        if self.calls == 1:
            return _DummyResponse(
                _DummyMessage(
                    content="",
                    tool_calls=[_DummyToolCall("call_1", "get_board_state", "{}")],
                )
            )
        return _DummyResponse(
            _DummyMessage(
                content=(
                    '{"start":{"row":7,"col":7},"direction":"ACROSS",'
                    '"placements":[{"row":7,"col":7,"letter":"A"}],"word":"A"}'
                ),
            )
        )


class _DummyCompletionsExplore:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        self.calls += 1
        if self.calls == 1:
            return _DummyResponse(
                _DummyMessage(
                    content="",
                    tool_calls=[_DummyToolCall("call_1", "validate_word_slovak", '{"word":"KOL"}')],
                )
            )
        return _DummyResponse(
            _DummyMessage(
                content=(
                    '{"start":{"row":7,"col":7},"direction":"ACROSS",'
                    '"placements":[{"row":7,"col":7,"letter":"K"}],"word":"K"}'
                ),
            )
        )


class _DummyCompletionsScored:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        self.calls += 1
        if self.calls == 1:
            return _DummyResponse(
                _DummyMessage(
                    content="",
                    tool_calls=[
                        _DummyToolCall(
                            "call_1",
                            "calculate_move_score",
                            '{"words":[{"word":"KOL"}],"placements":[]}',
                        )
                    ],
                )
            )
        if self.calls == 2:
            return _DummyResponse(
                _DummyMessage(
                    content=(
                        '{"start":{"row":7,"col":7},"direction":"ACROSS",'
                        '"placements":[{"row":7,"col":7,"letter":"K"}],"word":"KOL"}'
                    ),
                )
            )
        if self.calls == 3:
            return _DummyResponse(
                _DummyMessage(
                    content="",
                    tool_calls=[
                        _DummyToolCall(
                            "call_2",
                            "calculate_move_score",
                            '{"words":[{"word":"JOL"}],"placements":[]}',
                        )
                    ],
                )
            )
        return _DummyResponse(
            _DummyMessage(
                content=(
                    '{"start":{"row":7,"col":7},"direction":"ACROSS",'
                    '"placements":[{"row":7,"col":7,"letter":"J"}],"word":"JOL"}'
                ),
            )
        )


class _DummyChat:
    def __init__(self) -> None:
        self.completions = _DummyCompletions()


class _DummyChatExplore:
    def __init__(self) -> None:
        self.completions = _DummyCompletionsExplore()


class _DummyChatScored:
    def __init__(self) -> None:
        self.completions = _DummyCompletionsScored()


class _DummyOpenAI:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        del args, kwargs
        self.chat = _DummyChat()


class _DummyOpenAIExplore:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        del args, kwargs
        self.chat = _DummyChatExplore()


class _DummyOpenAIScored:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        del args, kwargs
        self.chat = _DummyChatScored()


@pytest.mark.asyncio
async def test_openai_tools_client_executes_tool_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scrabgpt.ai.openai_tools_client.OpenAI", _DummyOpenAI)
    client = OpenAIToolClient(api_key="test-key", timeout_seconds=30)
    updates: list[dict] = []

    result = await client.call_model(
        model_id="gpt-5.2",
        prompt="test prompt",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_board_state",
                    "description": "Get board",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        tool_context={
            "board_grid": ["." * 15 for _ in range(15)],
            "blanks": [],
        },
        progress_callback=updates.append,
    )

    assert result["status"] == "ok"
    assert result["tool_calls_executed"] == ["get_board_state"]
    assert '"placements"' in result["content"]
    statuses = [str(update.get("status")) for update in updates]
    assert "tool_use" in statuses
    assert "tool_result" in statuses


def test_openai_tool_schemas_have_items_for_all_arrays() -> None:
    def _walk(node, path: str, missing: list[str]) -> None:  # type: ignore[no-untyped-def]
        if isinstance(node, dict):
            if node.get("type") == "array" and "items" not in node:
                missing.append(path)
            for key, value in node.items():
                _walk(value, f"{path}.{key}", missing)
            return
        if isinstance(node, list):
            for idx, value in enumerate(node):
                _walk(value, f"{path}[{idx}]", missing)

    missing_paths: list[str] = []
    for tool in get_openai_tools():
        params = tool.get("function", {}).get("parameters", {})
        _walk(params, f"tool:{tool.get('function', {}).get('name', '?')}", missing_paths)

    assert missing_paths == []


@pytest.mark.asyncio
async def test_openai_tools_client_can_force_extra_exploration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scrabgpt.ai.openai_tools_client.OpenAI", _DummyOpenAIExplore)
    client = OpenAIToolClient(api_key="test-key", timeout_seconds=30)

    result = await client.call_model(
        model_id="gpt-5.2",
        prompt="test prompt",
        min_word_validations=2,
        round_timeout_seconds=5,
        request_timeout_seconds=20,
    )

    assert result["status"] == "ok"
    # First response validates one word only, so client should request another round.
    assert client.client.chat.completions.calls >= 3


@pytest.mark.asyncio
async def test_openai_tools_client_can_force_more_scored_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scrabgpt.ai.openai_tools_client.OpenAI", _DummyOpenAIScored)

    def _fake_execute_tool(name: str, args: dict, *, context=None):  # type: ignore[no-untyped-def]
        del context
        if name != "calculate_move_score":
            return {"ok": True}
        return {"total_score": 10, "words": args.get("words", [])}

    monkeypatch.setattr("scrabgpt.ai.openai_tools_client.execute_tool", _fake_execute_tool)
    client = OpenAIToolClient(api_key="test-key", timeout_seconds=30)

    result = await client.call_model(
        model_id="gpt-5.2",
        prompt="test prompt",
        min_word_validations=0,
        min_scored_candidates=2,
        round_timeout_seconds=5,
        request_timeout_seconds=20,
    )

    assert result["status"] == "ok"
    assert client.client.chat.completions.calls >= 4
