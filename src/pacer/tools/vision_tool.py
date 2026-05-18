from __future__ import annotations
import json
from pacer.tools.base import BaseTool
from pacer.llm.client import LLMClient

_SYSTEM = """You are an OCR + understanding assistant for Chinese high-school exam questions.
Extract the question stem, identify the subject, and describe any figures.
Output STRICT JSON only:
{"subject":"math|chinese|english|physics|chemistry|biology","stem":"<text>","figure_description":"<short>"}
"""


class VisionUnderstandImageTool(BaseTool):
    name = "vision_understand_image"
    description = "OCR and understand a photographed exam question."
    parameters = {
        "type": "object",
        "properties": {
            "image_base64": {"type": "string", "description": "base64-encoded JPEG"},
            "hint": {"type": "string", "description": "optional subject hint"},
        },
        "required": ["image_base64"],
    }
    is_readonly = True

    def __init__(self, llm: LLMClient, model: str):
        self.llm = llm
        self.model = model

    async def execute(self, *, image_base64: str, hint: str | None = None) -> dict:
        user_text = "请按 system 指令提取这道题目。" + (f"提示：可能是{hint}。" if hint else "")
        resp = await self.llm.chat_with_images(
            system=_SYSTEM, user_text=user_text,
            image_base64_list=[image_base64], model=self.model,
        )
        try:
            return json.loads(resp.text.strip())
        except json.JSONDecodeError:
            return {"subject": hint or "unknown", "stem": resp.text, "figure_description": ""}
