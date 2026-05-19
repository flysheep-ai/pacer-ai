from __future__ import annotations
from unittest.mock import AsyncMock, patch
import pytest
from pacer.llm.client import LLMClient, LLMMessage, StreamChunk


class _AsyncIter:
    """Helper: converts a regular iterable into an async iterator."""
    def __init__(self, items):
        self._it = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


def _make_stream_chunks(texts: list[str]):
    """Simulate Anthropic content_block_delta events with TextDelta-like objects."""
    class FakeTextDelta:
        def __init__(self, text):
            self.type = "text_delta"
            self.text = text

    events = []
    for t in texts:
        events.append(type("Event", (), {"type": "content_block_delta", "delta": FakeTextDelta(t)}))
    return events


@pytest.mark.asyncio
async def test_anthropic_chat_stream_yields_chunks():
    client = LLMClient(api_key="sk-test", model="claude-test")
    mock_stream = AsyncMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aiter__ = lambda s: _AsyncIter(_make_stream_chunks(["Hello", " world"]))
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    with patch.object(client._client.messages, "stream", return_value=mock_stream):
        chunks = []
        async for chunk in client.chat_stream([LLMMessage(role="user", content="hi")]):
            if chunk.delta_text:
                chunks.append(chunk.delta_text)
        assert "".join(chunks) == "Hello world"


@pytest.mark.asyncio
async def test_openai_chat_stream_yields_chunks():
    from pacer.llm.openai_client import OpenAICompatClient
    client = OpenAICompatClient(api_key="sk-test", base_url="https://test", model="test")

    class FakeDelta:
        def __init__(self, content): self.content = content; self.tool_calls = None
    class FakeChoice:
        def __init__(self, content, finish=None): self.delta = FakeDelta(content); self.finish_reason = finish
    class FakeChunk:
        def __init__(self, content, finish=None): self.choices = [FakeChoice(content, finish)]

    chunks_iter = _AsyncIter([FakeChunk("Hello"), FakeChunk(" world"), FakeChunk("", finish="stop")])

    mock_stream = AsyncMock()
    mock_stream.__aiter__ = lambda s: chunks_iter
    with patch.object(client._client.chat.completions, "create", new=AsyncMock(return_value=mock_stream)):
        chunks = []
        async for chunk in client.chat_stream([LLMMessage(role="user", content="hi")]):
            if chunk.delta_text:
                chunks.append(chunk.delta_text)
        assert "".join(chunks) == "Hello world"
