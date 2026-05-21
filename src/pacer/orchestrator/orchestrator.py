from __future__ import annotations
import logging
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from typing import Any
from sqlalchemy.orm import Session
from pacer.llm.client import LLMClient, LLMMessage
from pacer.skills.loader import SkillsLoader
from pacer.orchestrator.router import RouterLLM, RouteDecision
from pacer.agents.homeroom import build_homeroom_agent
from pacer.agents.subject_teacher import build_subject_teacher_agent
from pacer.agents.mood_companion import build_mood_agent
from pacer.memory.persistent import PersistentMemory
from pacer.agent.loop import AgentLoop, AgentResult
from pacer.config import get_settings

log = logging.getLogger("pacer.orchestrator")

_HANDOFF_DELIMITER = "\n\n---\n"


@dataclass
class OrchestratedResult:
    final_text: str
    agent_used: str
    subject: str | None
    route: RouteDecision
    inner: AgentResult
    trace: list[dict[str, Any]] | None = None  # combined trace when handoff occurred


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

    def _build_agent(self, route: RouteDecision) -> tuple[AgentLoop, str]:
        if route.intent == "subject_qa" and route.subject:
            agent = build_subject_teacher_agent(
                llm=self.llm, session_factory=self.session_factory,
                student_id=self.student_id, subject=route.subject,
                skills_loader=self.skills_loader,
                vision_model=self.vision_model,
            )
            return agent, "subject_teacher"
        if route.intent == "mood_support":
            agent = build_mood_agent(
                llm=self.llm, session_factory=self.session_factory,
                student_id=self.student_id,
            )
            return agent, "mood_companion"
        agent = build_homeroom_agent(
            llm=self.llm, session_factory=self.session_factory,
            student_id=self.student_id,
        )
        return agent, "homeroom"

    @staticmethod
    def _extract_text(user_message: str | list[dict[str, Any]]) -> str:
        if isinstance(user_message, str):
            return user_message
        return " ".join(b.get("text", "") for b in user_message if b.get("type") == "text")

    @staticmethod
    def _called_return_to_homeroom(trace: list[dict[str, Any]]) -> bool:
        return any(
            step.get("tool") == "return_to_homeroom" for step in trace
        )

    async def handle(
        self, user_message: str | list[dict[str, Any]], history: list[LLMMessage],
    ) -> OrchestratedResult:
        text = self._extract_text(user_message)
        route = await self.router.route(text)
        agent, agent_used = self._build_agent(route)
        recalled = self._recall_memories(text)
        result = await agent.run(user_message, history=history, recalled_memory_block=recalled)

        # Hand-back: if sub-agent asked to return to homeroom, run a wrap-up.
        combined_trace = list(result.trace)
        if (
            get_settings().handoff_enabled
            and agent_used in ("subject_teacher", "mood_companion")
            and self._called_return_to_homeroom(result.trace)
        ):
            homeroom = build_homeroom_agent(
                llm=self.llm, session_factory=self.session_factory,
                student_id=self.student_id, max_iterations=2,
            )
            wrap_prompt = (
                f"学科老师/心态师已完成任务，以下是他的回复：\n{result.final_text}\n\n"
                f"请用 1-2 句简短的话做总结或过渡，回到班主任角色继续对话。"
            )
            wrap = await homeroom.run(wrap_prompt, history=[], recalled_memory_block=None)
            combined_trace.extend(wrap.trace)
            return OrchestratedResult(
                final_text=result.final_text + _HANDOFF_DELIMITER + wrap.final_text,
                agent_used=agent_used, subject=route.subject, route=route,
                inner=wrap, trace=combined_trace,
            )

        return OrchestratedResult(
            final_text=result.final_text, agent_used=agent_used,
            subject=route.subject, route=route, inner=result,
            trace=combined_trace,
        )

    async def handle_streaming(
        self, user_message: str | list[dict[str, Any]], history: list[LLMMessage],
        on_delta: Callable[[str], Awaitable[None]],
    ) -> OrchestratedResult:
        text = self._extract_text(user_message)
        route = await self.router.route(text)
        agent, agent_used = self._build_agent(route)
        recalled = self._recall_memories(text)
        result = await agent.run_streaming(
            user_message, history=history, on_delta=on_delta, recalled_memory_block=recalled,
        )

        # Hand-back: if sub-agent asked to return to homeroom, run homeroom wrap-up.
        combined_trace = list(result.trace)
        if (
            get_settings().handoff_enabled
            and agent_used in ("subject_teacher", "mood_companion")
            and self._called_return_to_homeroom(result.trace)
        ):
            homeroom = build_homeroom_agent(
                llm=self.llm, session_factory=self.session_factory,
                student_id=self.student_id, max_iterations=2,
            )
            wrap_prompt = (
                f"学科老师/心态师已完成任务，以下是他的回复：\n{result.final_text}\n\n"
                f"请用 1-2 句简短的话做总结或过渡，回到班主任角色继续对话。"
            )
            wrap = await homeroom.run(wrap_prompt, history=[], recalled_memory_block=None)
            combined_trace.extend(wrap.trace)
            if wrap.final_text:
                await on_delta(_HANDOFF_DELIMITER + wrap.final_text)
            final_text = result.final_text + _HANDOFF_DELIMITER + wrap.final_text
            return OrchestratedResult(
                final_text=final_text, agent_used=agent_used,
                subject=route.subject, route=route, inner=wrap, trace=combined_trace,
            )

        return OrchestratedResult(
            final_text=result.final_text, agent_used=agent_used,
            subject=route.subject, route=route, inner=result,
            trace=combined_trace,
        )

    def _recall_memories(self, query: str) -> str | None:
        """Pre-fetch long-term memory and format as a context block.

        Agents no longer carry a `search_memory` tool by default (homeroom),
        because this pre-recall already injects the relevant entries. Subject
        and mood agents keep the tool for proactive lookups during a task.
        """
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
            log.exception("memory recall failed student=%s", self.student_id)
            return None
