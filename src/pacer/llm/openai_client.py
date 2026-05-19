from __future__ import annotations
from collections.abc import AsyncIterator
from typing import Any
from openai import AsyncOpenAI
import httpx
from pacer.llm.client import LLMMessage, LLMResponse, StreamChunk


def _anthropic_tools_to_openai(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    result = []
    for t in tools:
        result.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        })
    return result


class OpenAICompatClient:
    """LLM client that talks to OpenAI-compatible APIs (including proxies).

    Mirrors the LLMClient interface so it's a drop-in replacement.
    """

    def __init__(self, api_key: str, base_url: str, model: str, max_tokens: int = 4096):
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.AsyncClient(proxy=None),
        )
        self.model = model
        self.max_tokens = max_tokens

    def _build_messages(
        self, messages: list[LLMMessage], system: str | None,
    ) -> list[dict]:
        """Convert LLMMessages + optional system prompt to OpenAI-format dict list."""
        import json
        oai_msgs: list[dict] = []
        if system:
            oai_msgs.append({"role": "system", "content": system})
        for m in messages:
            if isinstance(m.content, list):
                blocks = m.content
                text_parts = [b["text"] for b in blocks if b["type"] == "text"]
                tool_calls = []
                for b in blocks:
                    if b["type"] == "tool_use":
                        tool_calls.append({
                            "id": b["id"], "type": "function",
                            "function": {
                                "name": b["name"],
                                "arguments": json.dumps(b["input"], ensure_ascii=False),
                            },
                        })
                    elif b["type"] == "tool_result":
                        oai_msgs.append({
                            "role": "tool",
                            "tool_call_id": b["tool_use_id"],
                            "content": str(b["content"]),
                        })
                if tool_calls:
                    tc_msg = {"role": "assistant", "content": "\n".join(text_parts) or None}
                    tc_msg["tool_calls"] = tool_calls
                    oai_msgs.append(tc_msg)
                elif text_parts and not any(b["type"] == "tool_result" for b in blocks):
                    oai_msgs.append({"role": m.role, "content": "\n".join(text_parts)})
                else:
                    # Check for image blocks in multimodal content
                    image_blocks = [b for b in blocks if b["type"] == "image"]
                    if image_blocks:
                        content_blocks: list[dict] = []
                        for b in blocks:
                            if b["type"] == "image":
                                content_blocks.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{b['source']['media_type']};base64,{b['source']['data']}"
                                    },
                                })
                            elif b["type"] == "text":
                                content_blocks.append({"type": "text", "text": b["text"]})
                        oai_msgs.append({"role": m.role, "content": content_blocks})
            else:
                oai_msgs.append({"role": m.role, "content": m.content})
        return oai_msgs

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        oai_msgs = self._build_messages(messages, system)

        kwargs: dict = {
            "model": model or self.model,
            "max_tokens": self.max_tokens,
            "messages": oai_msgs,
        }
        if tools:
            kwargs["tools"] = _anthropic_tools_to_openai(tools)

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        text = choice.message.content or ""
        tool_calls = []
        if choice.message.tool_calls:
            import json
            for tc in choice.message.tool_calls:
                try:
                    inp = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    inp = {}
                tool_calls.append({"id": tc.id, "name": tc.function.name, "input": inp})
        return LLMResponse(
            text=text, tool_calls=tool_calls,
            stop_reason=choice.finish_reason or "end_turn",
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
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
        oai_msgs = self._build_messages(messages, system)

        kwargs = {
            "model": model or self.model,
            "max_tokens": self.max_tokens,
            "messages": oai_msgs,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = _anthropic_tools_to_openai(tools)

        resp = await self._client.chat.completions.create(**kwargs)
        async for chunk in resp:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue
            delta = choice.delta
            if delta and delta.content:
                yield StreamChunk(delta_text=delta.content)
            if choice.finish_reason:
                yield StreamChunk(delta_text="", finish_reason=choice.finish_reason)

    async def chat_with_images(
        self, *, system: str, user_text: str,
        image_base64_list: list[str], model: str | None = None,
    ) -> LLMResponse:
        content: list[dict] = []
        for img in image_base64_list:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img}"},
            })
        content.append({"type": "text", "text": user_text})
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        resp = await self._client.chat.completions.create(
            model=model or self.model, max_tokens=self.max_tokens, messages=messages,
        )
        choice = resp.choices[0]
        return LLMResponse(
            text=choice.message.content or "", tool_calls=[],
            stop_reason=choice.finish_reason or "end_turn",
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            raw=resp,
        )
