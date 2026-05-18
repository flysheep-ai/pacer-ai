import pytest
from unittest.mock import AsyncMock, MagicMock
from pacer.agent.loop import AgentLoop, AgentResult
from pacer.tools.base import ToolRegistry, BaseTool


class _StubTool(BaseTool):
    name = "stub"
    description = "stub"
    parameters = {"type": "object", "properties": {}}
    is_readonly = True

    async def execute(self, **kwargs):
        return {"ok": True}


def _llm_response(text="", tool_calls=None, stop_reason="end_turn"):
    from pacer.llm.client import LLMResponse
    return LLMResponse(
        text=text, tool_calls=tool_calls or [],
        stop_reason=stop_reason, input_tokens=10, output_tokens=5, raw=None,
    )


@pytest.mark.asyncio
async def test_loop_returns_text_when_no_tool_calls():
    llm = MagicMock()
    llm.chat = AsyncMock(return_value=_llm_response(text="Hello!"))
    reg = ToolRegistry()
    loop = AgentLoop(llm=llm, tools=reg, system_prompt="You are a teacher.")
    result = await loop.run("Hi", history=[])
    assert isinstance(result, AgentResult)
    assert result.final_text == "Hello!"
    assert result.iterations == 1


@pytest.mark.asyncio
async def test_loop_executes_tool_then_returns():
    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=[
        _llm_response(
            tool_calls=[{"id": "t1", "name": "stub", "input": {}}],
            stop_reason="tool_use",
        ),
        _llm_response(text="done", stop_reason="end_turn"),
    ])
    reg = ToolRegistry()
    reg.register(_StubTool())
    loop = AgentLoop(llm=llm, tools=reg, system_prompt="sys")
    result = await loop.run("call stub", history=[])
    assert result.final_text == "done"
    assert result.iterations == 2
    assert any(step["tool"] == "stub" for step in result.trace)


@pytest.mark.asyncio
async def test_loop_terminates_at_max_iterations():
    llm = MagicMock()
    llm.chat = AsyncMock(return_value=_llm_response(
        tool_calls=[{"id": "t", "name": "stub", "input": {}}],
        stop_reason="tool_use",
    ))
    reg = ToolRegistry()
    reg.register(_StubTool())
    loop = AgentLoop(llm=llm, tools=reg, system_prompt="sys", max_iterations=3)
    result = await loop.run("loop", history=[])
    assert result.iterations == 3
    assert result.stopped_reason == "max_iterations"
