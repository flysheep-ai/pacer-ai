from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]
    is_readonly: bool = True
    repeatable: bool = True

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        ...

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def to_anthropic_schemas(self) -> list[dict[str, Any]]:
        return [t.to_anthropic_schema() for t in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"status": "error", "error": f"unknown tool: {name}"}
        try:
            result = await tool.execute(**params)
            return {"status": "ok", "result": result}
        except Exception as exc:
            return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
