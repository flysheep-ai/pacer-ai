from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, timezone
from pacer.tools.base import BaseTool, StudentScopedTool
from pacer.db.models import ErrorRecord, Question, KnowledgePoint
from pacer.llm.client import LLMMessage

log = logging.getLogger("pacer.tools")


async def _classify_kp(error_id: int, stem: str, subject: str, sess, llm) -> None:
    """Best-effort: classify an error stem into 1-2 knowledge_point_ids."""
    try:
        kps = sess.query(KnowledgePoint).filter_by(subject=subject).all()
        if not kps:
            return
        kp_list = "\n".join(f"- id={kp.id} name={kp.point_name}" for kp in kps)
        prompt = (
            f"题目: {stem[:300]}\n"
            f"可用知识点:\n{kp_list}\n\n"
            f"请选出最相关的 1-2 个知识点 id，严格的 JSON 数组返回，如 [101, 204]。"
        )
        resp = await llm.chat(
            [LLMMessage(role="user", content=prompt)],
            system="你是一个学科分类助手。只输出 JSON 数组。",
        )
        ids = json.loads(resp.text.strip())
        if isinstance(ids, list) and len(ids) > 0:
            ids = [int(i) for i in ids if isinstance(i, (int, float))]
            if ids:
                e = sess.get(ErrorRecord, error_id)
                if e is not None:
                    e.knowledge_point_ids = ids
                    sess.commit()
    except Exception:
        log.debug("KP auto-classify failed for error %s", error_id, exc_info=True)


class SaveErrorRecordTool(StudentScopedTool):
    name = "save_error_record"
    description = "Persist an error record for the student."
    parameters = {
        "type": "object",
        "properties": {
            "question_id": {"type": ["integer", "null"]},
            "stem_text": {"type": "string"},
            "user_answer": {"type": "string"},
            "correct_answer": {"type": "string"},
            "error_type": {"type": "string", "enum": ["carelessness", "concept", "method", "other"]},
            "knowledge_point_ids": {"type": "array", "items": {"type": "integer"}},
            "source": {"type": "string", "enum": ["photo", "text", "qa"]},
            "explanation_text": {"type": "string"},
            "subject": {"type": "string"},
        },
        "required": ["stem_text", "user_answer", "correct_answer", "error_type", "source"],
    }
    is_readonly = False

    def __init__(self, session_factory, student_id, llm=None):
        super().__init__(session_factory, student_id)
        self._llm = llm

    async def execute(self, *, stem_text: str, user_answer: str, correct_answer: str,
                      error_type: str, source: str, question_id: int | None = None,
                      knowledge_point_ids: list[int] | None = None,
                      explanation_text: str = "", subject: str = "") -> dict:
        sess = self._session_factory()
        if question_id is None and subject:
            q = Question(subject=subject, stem=stem_text, answer=correct_answer,
                         knowledge_point_ids=knowledge_point_ids or [])
            sess.add(q); sess.flush(); question_id = q.id
        e = ErrorRecord(
            student_id=self._student_id, question_id=question_id,
            user_answer=user_answer, correct_answer=correct_answer,
            error_type=error_type, knowledge_point_ids=knowledge_point_ids or [],
            source=source, explanation_text=explanation_text,
        )
        sess.add(e); sess.commit(); sess.refresh(e)

        # Best-effort async KP auto-classification (fire-and-forget)
        if self._llm is not None and subject:
            try:
                asyncio.create_task(_classify_kp(e.id, stem_text, subject, sess, self._llm))
            except RuntimeError:
                pass

        return {"error_id": e.id}


class GetRecentErrorsTool(StudentScopedTool):
    name = "get_recent_errors"
    description = "Fetch the student's recent error records."
    parameters = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 10},
            "subject": {"type": "string"},
            "since_days": {"type": "integer", "default": 7},
        },
    }
    is_readonly = True

    async def execute(self, *, limit: int = 10, subject: str | None = None,
                      since_days: int = 7) -> dict:
        sess = self._session_factory()
        q = sess.query(ErrorRecord).filter_by(student_id=self._student_id)
        if subject:
            q = q.join(Question, ErrorRecord.question_id == Question.id, isouter=True)
            q = q.filter(Question.subject == subject)
        rows = q.order_by(ErrorRecord.created_at.desc()).limit(limit).all()
        return {"errors": [
            {"id": e.id, "stem": e.question.stem if e.question else None,
             "user_answer": e.user_answer, "correct_answer": e.correct_answer,
             "error_type": e.error_type, "mastery_level": e.mastery_level,
             "review_count": e.review_count}
            for e in rows
        ]}


class GenerateVariantTool(BaseTool):
    name = "generate_variant"
    description = "Generate a variant question for practice based on an error."
    parameters = {
        "type": "object",
        "properties": {
            "original_stem": {"type": "string"},
            "topic": {"type": "string"},
        },
        "required": ["original_stem"],
    }
    is_readonly = True

    def __init__(self, llm):
        self.llm = llm

    async def execute(self, *, original_stem: str, topic: str = "") -> dict:
        prompt = f"Generate a variant practice question for:\n{original_stem}" + \
                 (f"\nTopic: {topic}" if topic else "")
        resp = await self.llm.chat(
            [LLMMessage(role="user", content=prompt)],
            system="Output a variant exam question (stem + expected answer) in Chinese.",
        )
        return {"variant": resp.text}


class MarkErrorReviewedTool(StudentScopedTool):
    name = "mark_error_reviewed"
    description = "Mark an error record as reviewed."
    parameters = {
        "type": "object",
        "properties": {
            "error_record_id": {"type": "integer"},
            "correct": {"type": "boolean"},
        },
        "required": ["error_record_id", "correct"],
    }
    is_readonly = False

    async def execute(self, *, error_record_id: int, correct: bool) -> dict:
        sess = self._session_factory()
        e = sess.get(ErrorRecord, error_record_id)
        if e is None:
            return {"status": "not_found"}
        e.review_count += 1
        e.last_reviewed_at = datetime.now(timezone.utc)
        delta = 0.15 if correct else -0.10
        e.mastery_level = max(0.0, min(1.0, e.mastery_level + delta))
        sess.commit()
        return {"reviewed": True, "new_mastery": e.mastery_level}
