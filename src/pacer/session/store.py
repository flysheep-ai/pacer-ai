from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from pacer.db.models import ChatSession, Message


class SessionStore:
    def __init__(self, session: Session):
        self._session = session

    def create_session(self, *, student_id: int) -> ChatSession:
        chat = ChatSession(
            student_id=student_id, status="active",
            last_active_at=datetime.now(timezone.utc),
        )
        self._session.add(chat)
        self._session.commit()
        self._session.refresh(chat)
        return chat

    def get_session(self, session_id: int) -> ChatSession | None:
        return self._session.get(ChatSession, session_id)

    def append_message(
        self, session_id: int, *, role: str, agent: str | None,
        content: str, metadata: dict | None = None,
    ) -> Message:
        m = Message(
            session_id=session_id, role=role, agent=agent,
            content=content, metadata_json=metadata or {},
        )
        self._session.add(m)
        chat = self.get_session(session_id)
        if chat is not None:
            chat.last_active_at = datetime.now(timezone.utc)
        self._session.commit()
        self._session.refresh(m)
        return m

    def list_messages(self, session_id: int) -> list[Message]:
        return (
            self._session.query(Message)
            .filter_by(session_id=session_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .all()
        )

    def history_for_llm(self, session_id: int) -> list[dict]:
        return [
            {"role": m.role, "content": m.content}
            for m in self.list_messages(session_id)
            if m.role in ("user", "assistant")
        ]
