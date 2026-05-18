from __future__ import annotations
from pacer.tools.base import BaseTool
from pacer.skills.loader import SkillsLoader


class LoadSkillTool(BaseTool):
    name = "load_skill"
    description = "Load full skill documentation by name."
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    is_readonly = True

    def __init__(self, loader: SkillsLoader):
        self.loader = loader

    async def execute(self, *, name: str) -> dict:
        body = self.loader.load(name)
        if body is None:
            return {"status": "not_found", "name": name}
        return {"name": name, "body": body}


class ListSkillsTool(BaseTool):
    name = "list_skills"
    description = "List available skills, optionally filtered by subject."
    parameters = {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "math/chinese/english/physics/chemistry/biology",
            },
        },
    }
    is_readonly = True

    def __init__(self, loader: SkillsLoader):
        self.loader = loader

    async def execute(self, *, subject: str | None = None) -> dict:
        skills = self.loader.list_skills(subject=subject)
        return {"skills": [
            {"name": s.name, "subject": s.subject, "chapter": s.chapter, "description": s.description}
            for s in skills
        ]}
