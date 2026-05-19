from __future__ import annotations
from typing import Any
from openai import AsyncOpenAI
from pacer.llm.client import LLMMessage, LLMResponse


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


def _openai_msg(m: LLMMessage) -> dict:
    if isinstance(m.content, str):
        return {"role": m.role, "content": m.content}
    # content is a list of blocks (tool_use / tool_result etc)
    blocks = m.content
    # Separate text and tool_use
    text_parts = [b["text"] for b in blocks if b["type"] == "text"]
    tool_calls = []
    for b in blocks:
        if b["type"] == "tool_use":
            tool_calls.append({
                "id": b["id"],
                "type": "function",
                "function": {"name": b["name"], "arguments": str(b["input"])},
            })
        elif b["type"] == "tool_result":
            tool_calls.append({
                "role": "tool",
                "tool_call_id": b["tool_use_id"],
                "content": b["content"],
            })
    msg: dict = {"role": m.role}
    if text_parts:
        msg["content"] = "\n".join(text_parts)
    if tool_calls:
        # Separate tool_calls from tool results
        real_tool_calls = [t for t in tool_calls if "type" in t]
        tool_results = [t for t in tool_calls if "role" in t]
        if real_tool_calls:
            msg["tool_calls"] = real_tool_calls
        if tool_results:
            msg = tool_results[0]  # tool message
        if not real_tool_calls and not tool_results:
            msg["content"] = msg.get("content", "")
    if not msg.get("content") and not tool_calls:
        msg["content"] = ""
    return msg


class OpenAICompatClient:
    """LLM client that talks to OpenAI-compatible APIs (including proxies).

    Mirrors the LLMClient interface so it's a drop-in replacement.
    """

    def __init__(self, api_key: str, base_url: str, model: str, max_tokens: int = 4096):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
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
        oai_msgs: list[dict] = []
        if system:
            oai_msgs.append({"role": "system", "content": system})
        # For the last assistant message with tool_use, convert properly
        for m in messages:
            if isinstance(m.content, list):
                blocks = m.content
                text_parts = [b["text"] for b in blocks if b["type"] == "text"]
                tool_calls = []
                for b in blocks:
                    if b["type"] == "tool_use":
                        import json
                        tool_calls.append({
                            "id": b["id"],
                            "type": "function",
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
                oai_msgs.append({"role": m.role, "content": m.content})

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
