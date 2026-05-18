from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Literal
from pacer.llm.client import LLMClient, LLMMessage
from pacer.orchestrator.prompts import ROUTER_SYSTEM, SUBJECT_KEYWORD_MAP

Intent = Literal["subject_qa", "mood_support", "planning", "chitchat"]


@dataclass
class RouteDecision:
    intent: Intent
    subject: str | None
    confidence: float


class RouterLLM:
    def __init__(self, llm: LLMClient, model: str):
        self.llm = llm
        self.model = model

    async def route(self, text: str) -> RouteDecision:
        resp = await self.llm.chat(
            [LLMMessage(role="user", content=text)],
            system=ROUTER_SYSTEM,
            model=self.model,
        )
        decision = self._parse(resp.text)
        return self._apply_rules(text, decision)

    def _parse(self, raw: str) -> RouteDecision:
        try:
            data = json.loads(raw.strip())
            intent = data.get("intent", "chitchat")
            if intent not in ("subject_qa", "mood_support", "planning", "chitchat"):
                intent = "chitchat"
            return RouteDecision(
                intent=intent,
                subject=data.get("subject") if data.get("subject") != "null" else None,
                confidence=float(data.get("confidence", 0.5)),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return RouteDecision(intent="chitchat", subject=None, confidence=0.0)

    def _apply_rules(self, text: str, decision: RouteDecision) -> RouteDecision:
        lower = text.lower()
        for kw, subj in SUBJECT_KEYWORD_MAP.items():
            if kw in text or kw in lower:
                return RouteDecision(
                    intent="subject_qa", subject=subj,
                    confidence=max(decision.confidence, 0.85),
                )
        return decision
