from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.llm.client import LLMClient, LLMMessage
from pacer.skills.loader import SkillsLoader
from pacer.orchestrator.router import RouterLLM, RouteDecision
from pacer.agents.homeroom import build_homeroom_agent
from pacer.agents.subject_teacher import build_subject_teacher_agent
from pacer.agents.mood_companion import build_mood_agent
from pacer.agent.loop import AgentResult


@dataclass
class OrchestratedResult:
    final_text: str
    agent_used: str
    subject: str | None
    route: RouteDecision
    inner: AgentResult


class Orchestrator:
    def __init__(
        self, *, llm: LLMClient, router_model: str,
        session_factory: Callable[[], Session], student_id: int,
        skills_loader: SkillsLoader, vision_model: str | None = None,
    ):
        self.llm = llm
        self.router = RouterLLM(llm=llm, model=router_model)
        self.session_factory = session_factory
        self.student_id = student_id
        self.skills_loader = skills_loader
        self.vision_model = vision_model or llm.model

    async def handle(
        self, user_message: str, history: list[LLMMessage],
    ) -> OrchestratedResult:
        route = await self.router.route(user_message)

        if route.intent == "subject_qa" and route.subject:
            agent = build_subject_teacher_agent(
                llm=self.llm, session_factory=self.session_factory,
                student_id=self.student_id, subject=route.subject,
                skills_loader=self.skills_loader,
                vision_model=self.vision_model,
            )
            agent_used = "subject_teacher"
        elif route.intent == "mood_support":
            agent = build_mood_agent(
                llm=self.llm, session_factory=self.session_factory,
                student_id=self.student_id,
            )
            agent_used = "mood_companion"
        else:
            agent = build_homeroom_agent(
                llm=self.llm, session_factory=self.session_factory,
                student_id=self.student_id,
            )
            agent_used = "homeroom"

        result = await agent.run(user_message, history=history)
        return OrchestratedResult(
            final_text=result.final_text, agent_used=agent_used,
            subject=route.subject, route=route, inner=result,
        )
