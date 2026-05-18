import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pacer.llm.client import LLMClient, LLMMessage


@pytest.mark.asyncio
async def test_chat_returns_assistant_text():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(type="text", text="Hello, student!")]
    fake_response.stop_reason = "end_turn"
    fake_response.usage = MagicMock(input_tokens=10, output_tokens=5)

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=fake_response)

    with patch("pacer.llm.client.AsyncAnthropic", return_value=mock_client):
        llm = LLMClient(api_key="sk-test", model="claude-sonnet-4-6")
        result = await llm.chat([LLMMessage(role="user", content="Hi")])

    assert result.text == "Hello, student!"
    assert result.stop_reason == "end_turn"
    assert result.input_tokens == 10
    assert result.output_tokens == 5


@pytest.mark.asyncio
async def test_chat_passes_system_prompt():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(type="text", text="ok")]
    fake_response.stop_reason = "end_turn"
    fake_response.usage = MagicMock(input_tokens=1, output_tokens=1)

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=fake_response)

    with patch("pacer.llm.client.AsyncAnthropic", return_value=mock_client):
        llm = LLMClient(api_key="sk-test", model="claude-sonnet-4-6")
        await llm.chat(
            [LLMMessage(role="user", content="Hi")],
            system="You are a teacher.",
        )

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "You are a teacher."
    assert call_kwargs["model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_chat_parses_tool_use_blocks():
    from collections import namedtuple
    Block = namedtuple("Block", ["type", "text", "id", "name", "input"], defaults=[None] * 5)

    usage = namedtuple("Usage", ["input_tokens", "output_tokens"])(10, 5)
    fake_response = MagicMock()
    fake_response.content = [
        Block(type="tool_use", id="t1", name="echo", input={"text": "hi"}, text=None),
        Block(type="text", text="Using echo tool...", id=None, name=None, input=None),
    ]
    fake_response.stop_reason = "tool_use"
    fake_response.usage = usage

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=fake_response)

    with patch("pacer.llm.client.AsyncAnthropic", return_value=mock_client):
        llm = LLMClient(api_key="sk-test", model="claude-sonnet-4-6")
        result = await llm.chat([LLMMessage(role="user", content="Echo hi")])

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "echo"
    assert result.tool_calls[0]["input"] == {"text": "hi"}
