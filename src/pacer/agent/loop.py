from __future__ import annotations
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from pacer.llm.client import LLMClient, LLMMessage, LLMResponse
from pacer.tools.base import ToolRegistry
from pacer.agent.context import build_messages

log = logging.getLogger("pacer.agent")


@dataclass
class AgentResult:
    final_text: str
    iterations: int
    trace: list[dict[str, Any]] = field(default_factory=list)
    stopped_reason: str = "end_turn"
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class AgentLoop:
    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        system_prompt: str,
        max_iterations: int = 8,
    ):
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations

    def _tool_schemas(self) -> list[dict[str, Any]] | None:
        return self.tools.to_anthropic_schemas() or None

    async def _apply_tool_calls(
        self,
        resp: LLMResponse,
        messages: list[LLMMessage],
        trace: list[dict[str, Any]],
    ) -> None:
        """Append assistant tool_use + user tool_result blocks for a turn."""
        assistant_content: list[dict[str, Any]] = []
        if resp.text:
            assistant_content.append({"type": "text", "text": resp.text})
        for tc in resp.tool_calls:
            assistant_content.append({
                "type": "tool_use", "id": tc["id"],
                "name": tc["name"], "input": tc["input"],
            })
        messages.append(LLMMessage(role="assistant", content=assistant_content))

        tool_results: list[dict[str, Any]] = []
        for tc in resp.tool_calls:
            exec_result = await self.tools.execute(tc["name"], tc["input"])
            trace.append({"tool": tc["name"], "input": tc["input"], "result": exec_result})
            tool_results.append({
                "type": "tool_result", "tool_use_id": tc["id"],
                "content": str(exec_result),
            })
        messages.append(LLMMessage(role="user", content=tool_results))

    async def run(
        self,
        user_message: str | list[dict[str, Any]],
        history: list[LLMMessage],
        recalled_memory_block: str | None = None,
    ) -> AgentResult:
        messages = build_messages(user_message, history, recalled_memory_block)
        trace: list[dict[str, Any]] = []
        total_in = total_out = 0
        for i in range(1, self.max_iterations + 1):
            resp = await self.llm.chat(
                messages, system=self.system_prompt, tools=self._tool_schemas(),
            )
            total_in += resp.input_tokens
            total_out += resp.output_tokens
            if not resp.tool_calls:
                return AgentResult(
                    final_text=resp.text, iterations=i, trace=trace,
                    stopped_reason=resp.stop_reason,
                    total_input_tokens=total_in, total_output_tokens=total_out,
                )
            await self._apply_tool_calls(resp, messages, trace)

        return AgentResult(
            final_text="", iterations=self.max_iterations, trace=trace,
            stopped_reason="max_iterations",
            total_input_tokens=total_in, total_output_tokens=total_out,
        )

    async def run_streaming(
        self,
        user_message: str | list[dict[str, Any]],
        history: list[LLMMessage],
        on_delta: Callable[[str], Awaitable[None]],
        recalled_memory_block: str | None = None,
    ) -> AgentResult:
        """Streaming variant.

        Tool-using turns are non-streaming (clients don't yet surface tool_use
        deltas). On the first text-only turn we emit the response in small
        chunks so the UI keeps its typewriter feel without losing tool_use.
        """
        messages = build_messages(user_message, history, recalled_memory_block)
        trace: list[dict[str, Any]] = []
        total_in = total_out = 0
        last_text = ""
        for i in range(1, self.max_iterations + 1):
            resp = await self.llm.chat(
                messages, system=self.system_prompt, tools=self._tool_schemas(),
            )
            total_in += resp.input_tokens
            total_out += resp.output_tokens
            if not resp.tool_calls:
                last_text = resp.text
                await _emit_in_chunks(resp.text, on_delta)
                return AgentResult(
                    final_text=resp.text, iterations=i, trace=trace,
                    stopped_reason=resp.stop_reason,
                    total_input_tokens=total_in, total_output_tokens=total_out,
                )
            await self._apply_tool_calls(resp, messages, trace)

        log.warning("agent loop hit max_iterations=%d without final text", self.max_iterations)
        return AgentResult(
            final_text=last_text, iterations=self.max_iterations, trace=trace,
            stopped_reason="max_iterations",
            total_input_tokens=total_in, total_output_tokens=total_out,
        )


async def _emit_in_chunks(text: str, on_delta: Callable[[str], Awaitable[None]], chunk_size: int = 24) -> None:
    """Emit text in small slices to keep the SSE UX feeling streamed."""
    if not text:
        return
    if len(text) <= chunk_size:
        await on_delta(text)
        return
    for i in range(0, len(text), chunk_size):
        await on_delta(text[i:i + chunk_size])
