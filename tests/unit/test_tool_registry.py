import pytest
from pacer.tools.base import BaseTool, ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo back the input"
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }
    is_readonly = True

    async def execute(self, *, text: str) -> dict:
        return {"echo": text}


class FailingTool(BaseTool):
    name = "fail"
    description = "Always fails"
    parameters = {"type": "object", "properties": {}}
    is_readonly = True

    async def execute(self, **kwargs):
        raise ValueError("intentional")


@pytest.mark.asyncio
async def test_registry_executes_tool():
    reg = ToolRegistry()
    reg.register(EchoTool())
    result = await reg.execute("echo", {"text": "hi"})
    assert result == {"status": "ok", "result": {"echo": "hi"}}


@pytest.mark.asyncio
async def test_registry_wraps_errors():
    reg = ToolRegistry()
    reg.register(FailingTool())
    result = await reg.execute("fail", {})
    assert result["status"] == "error"
    assert "intentional" in result["error"]


@pytest.mark.asyncio
async def test_unknown_tool_returns_error():
    reg = ToolRegistry()
    result = await reg.execute("ghost", {})
    assert result["status"] == "error"
    assert "unknown" in result["error"].lower()


def test_to_anthropic_schemas():
    reg = ToolRegistry()
    reg.register(EchoTool())
    schemas = reg.to_anthropic_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "echo"
    assert schemas[0]["description"] == "Echo back the input"
    assert schemas[0]["input_schema"]["required"] == ["text"]
