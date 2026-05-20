from __future__ import annotations
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable
from anthropic import AsyncAnthropic


@dataclass
class LLMMessage:
    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]


@dataclass
class StreamChunk:
    delta_text: str
    tool_call_delta: dict[str, Any] | None = None
    finish_reason: str | None = None


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict[str, Any]]
    stop_reason: str
    input_tokens: int
    output_tokens: int
    raw: Any


@runtime_checkable
class LLMClientProtocol(Protocol):
    model: str

    async def chat(
        self, messages: list[LLMMessage], *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> LLMResponse: ...

    def chat_stream(
        self, messages: list[LLMMessage], *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]: ...

    async def chat_with_images(
        self, *, system: str, user_text: str,
        image_base64_list: list[str], model: str | None = None,
    ) -> LLMResponse: ...


class LLMClient:
    def __init__(self, api_key: str, model: str, max_tokens: int = 4096):
        self._client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        resp = await self._client.messages.create(**kwargs)
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({"id": block.id, "name": block.name, "input": block.input})
        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=resp.stop_reason,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            raw=resp,
        )

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                # Only emit text deltas for now; tool_call_delta streaming is a future phase
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield StreamChunk(delta_text=event.delta.text)
            final_msg = await stream.get_final_message()
            yield StreamChunk(delta_text="", finish_reason=final_msg.stop_reason)

    async def chat_with_images(
        self,
        *,
        system: str,
        user_text: str,
        image_base64_list: list[str],
        model: str | None = None,
    ) -> LLMResponse:
        content_blocks: list[dict[str, Any]] = []
        for img in image_base64_list:
            content_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": img},
            })
        content_blocks.append({"type": "text", "text": user_text})
        resp = await self._client.messages.create(
            model=model or self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": content_blocks}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return LLMResponse(
            text=text, tool_calls=[], stop_reason=resp.stop_reason,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            raw=resp,
        )
