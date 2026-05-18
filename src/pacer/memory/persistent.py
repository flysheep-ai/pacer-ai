from __future__ import annotations
import re
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pacer.db.models import MemoryEntry


_CJK_RE = re.compile(r"[一-鿿]")
_ASCII_RE = re.compile(r"[A-Za-z]{3,}")


def _tokenize(text: str) -> list[str]:
    tokens = _ASCII_RE.findall(text.lower())
    tokens += _CJK_RE.findall(text)
    return tokens


class PersistentMemory:
    """DB-backed long-term memory scoped to a single student."""

    def __init__(self, session: Session, student_id: int):
        self._session = session
        self._student_id = student_id

    def add(self, *, type: str, key: str, content: str, importance: float = 0.5) -> MemoryEntry:
        entry = MemoryEntry(
            student_id=self._student_id,
            type=type, key=key, content=content, importance=importance,
        )
        self._session.add(entry)
        self._session.commit()
        self._session.refresh(entry)
        return entry

    def find_relevant(self, query: str, *, max_results: int = 3) -> list[MemoryEntry]:
        tokens = _tokenize(query)
        if not tokens:
            return []
        conds = [MemoryEntry.content.ilike(f"%{t}%") for t in tokens] + \
                [MemoryEntry.key.ilike(f"%{t}%") for t in tokens]
        rows = (
            self._session.query(MemoryEntry)
            .filter(MemoryEntry.student_id == self._student_id, or_(*conds))
            .all()
        )

        def score(entry: MemoryEntry) -> float:
            blob = (entry.content + " " + entry.key).lower()
            tok_hits = sum(1 for t in tokens if t.lower() in blob)
            return tok_hits + entry.importance

        rows.sort(key=score, reverse=True)
        return rows[:max_results]
