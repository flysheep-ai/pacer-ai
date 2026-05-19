from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from sqlalchemy.orm import Session
from pacer.llm.client import LLMClient, LLMMessage
from pacer.skills.loader import SkillsLoader
from pacer.orchestrator.router import RouterLLM, RouteDecision
from pacer.agents.homeroom import build_homeroom_agent
from pacer.agents.subject_teacher import build_subject_teacher_agent
from pacer.agents.mood_companion import build_mood_agent
from pacer.memory.persistent import PersistentMemory
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

        recalled = self._recall_memories(user_message)
        result = await agent.run(user_message, history=history, recalled_memory_block=recalled)
        return OrchestratedResult(
            final_text=result.final_text, agent_used=agent_used,
            subject=route.subject, route=route, inner=result,
        )

    async def handle_streaming(
        self, user_message: str | list[dict[str, Any]], history: list[LLMMessage],
        on_delta: Callable[[str], Awaitable[None]],
    ) -> OrchestratedResult:
        route_text = user_message if isinstance(user_message, str) else " ".join(b.get("text", "") for b in user_message if b.get("type") == "text")
        route = await self.router.route(route_text)

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

        recalled = self._recall_memories(route_text)
        result = await agent.run_streaming(user_message, history=history, on_delta=on_delta, recalled_memory_block=recalled)
        return OrchestratedResult(
            final_text=result.final_text, agent_used=agent_used,
            subject=route.subject, route=route, inner=result,
        )

    def _recall_memories(self, query: str) -> str | None:
        """Search long-term memory for relevant entries and format as context block."""
        try:
            session = self.session_factory()
            mem = PersistentMemory(session, self.student_id)
            entries = mem.find_relevant(query, max_results=5)
            if not entries:
                return None
            lines = ["<recalled-memories>"]
            for e in entries:
                lines.append(f"- [{e.type}] {e.key}: {e.content}")
            lines.append("</recalled-memories>")
            return "\n".join(lines)
        except Exception:
            return None
