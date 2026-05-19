from __future__ import annotations
import re
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pacer.db.models import MemoryEntry
from pacer.memory.embedding import encode, cosine_similarity, embedding_to_json, embedding_from_json


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
        text_for_embed = f"{key}: {content}"
        try:
            emb_json = embedding_to_json(encode(text_for_embed))
        except Exception:
            emb_json = None
        entry = MemoryEntry(
            student_id=self._student_id,
            type=type, key=key, content=content, importance=importance,
            embedding_json=emb_json,
        )
        self._session.add(entry)
        self._session.commit()
        self._session.refresh(entry)
        return entry

    def find_by_key_and_type(self, key: str, type: str) -> MemoryEntry | None:
        """Check if a memory with the same key+type already exists."""
        return (
            self._session.query(MemoryEntry)
            .filter_by(student_id=self._student_id, key=key, type=type)
            .first()
        )

    def update_embedding(self, entry_id: int, content: str, key: str = "") -> None:
        """Re-encode and update embedding for an existing entry."""
        text_for_embed = f"{key}: {content}"
        try:
            emb_json = embedding_to_json(encode(text_for_embed))
            entry = self._session.get(MemoryEntry, entry_id)
            if entry:
                entry.embedding_json = emb_json
                self._session.commit()
        except Exception:
            pass

    def find_relevant(self, query: str, *, max_results: int = 5) -> list[MemoryEntry]:
        # First, try semantic search via embeddings
        try:
            query_vec = encode(query)
        except Exception:
            query_vec = None

        # Fetch all entries with embeddings for this student
        rows = (
            self._session.query(MemoryEntry)
            .filter(MemoryEntry.student_id == self._student_id)
            .all()
        )

        if query_vec is not None:
            # Score by cosine similarity to query embedding, boosted by importance
            scored = []
            for r in rows:
                emb = embedding_from_json(r.embedding_json or "")
                if emb is None:
                    continue
                sim = cosine_similarity(query_vec, emb)
                scored.append((sim + r.importance * 0.3, r))
            if scored:
                scored.sort(key=lambda x: x[0], reverse=True)
                return [s[1] for s in scored[:max_results]]

        # Fallback: keyword search
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
