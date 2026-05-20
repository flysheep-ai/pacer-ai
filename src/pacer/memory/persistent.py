from __future__ import annotations
import logging
import re
from typing import Iterable

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc

from pacer.db.models import MemoryEntry
from pacer.memory.embedding import (
    bytes_to_vec, cosine_similarity, embedding_from_json, encode, vec_to_bytes,
)

log = logging.getLogger("pacer.memory")

_CJK_RE = re.compile(r"[一-鿿]")
_ASCII_RE = re.compile(r"[A-Za-z]{3,}")
_DUPLICATE_THRESHOLD = 0.92  # cosine sim above this → treat as duplicate
_CANDIDATE_LIMIT = 500       # cap for in-memory vector scoring


def _tokenize(text: str) -> list[str]:
    tokens = _ASCII_RE.findall(text.lower())
    tokens += _CJK_RE.findall(text)
    return tokens


class PersistentMemory:
    """DB-backed long-term memory scoped to a single student."""

    def __init__(self, session: Session, student_id: int):
        self._session = session
        self._student_id = student_id

    # ---- writes -----------------------------------------------------------

    def _encode(self, text: str) -> np.ndarray | None:
        try:
            return encode(text)
        except Exception:
            log.exception("embedding encode failed")
            return None

    def add(self, *, type: str, key: str, content: str, importance: float = 0.5) -> MemoryEntry:
        vec = self._encode(f"{key}: {content}")
        entry = MemoryEntry(
            student_id=self._student_id,
            type=type, key=key, content=content, importance=importance,
            embedding_blob=vec_to_bytes(vec) if vec is not None else None,
            embedding_dim=int(vec.shape[0]) if vec is not None else None,
        )
        self._session.add(entry)
        self._session.commit()
        self._session.refresh(entry)
        return entry

    def add_if_novel(
        self, *, type: str, key: str, content: str, importance: float = 0.5,
    ) -> tuple[MemoryEntry | None, str]:
        """Add an entry unless an existing one is near-duplicate.

        Returns (entry_or_None, reason). reason ∈ {"added","duplicate_key","duplicate_semantic"}.
        """
        if self.find_by_key_and_type(key, type) is not None:
            return None, "duplicate_key"
        vec = self._encode(f"{key}: {content}")
        if vec is not None:
            for other_vec, other in self._iter_vectors(limit=_CANDIDATE_LIMIT):
                if cosine_similarity(vec, other_vec) >= _DUPLICATE_THRESHOLD:
                    return None, "duplicate_semantic"
        entry = MemoryEntry(
            student_id=self._student_id,
            type=type, key=key, content=content, importance=importance,
            embedding_blob=vec_to_bytes(vec) if vec is not None else None,
            embedding_dim=int(vec.shape[0]) if vec is not None else None,
        )
        self._session.add(entry)
        self._session.commit()
        self._session.refresh(entry)
        return entry, "added"

    def find_by_key_and_type(self, key: str, type: str) -> MemoryEntry | None:
        return (
            self._session.query(MemoryEntry)
            .filter_by(student_id=self._student_id, key=key, type=type)
            .first()
        )

    def update_embedding(self, entry_id: int, content: str, key: str = "") -> None:
        vec = self._encode(f"{key}: {content}")
        entry = self._session.get(MemoryEntry, entry_id)
        if entry is None or vec is None:
            return
        entry.embedding_blob = vec_to_bytes(vec)
        entry.embedding_dim = int(vec.shape[0])
        self._session.commit()

    # ---- reads ------------------------------------------------------------

    def _iter_vectors(self, *, limit: int) -> Iterable[tuple[np.ndarray, MemoryEntry]]:
        rows = (
            self._session.query(MemoryEntry)
            .filter(MemoryEntry.student_id == self._student_id)
            .order_by(desc(MemoryEntry.importance), desc(MemoryEntry.updated_at))
            .limit(limit)
            .all()
        )
        for r in rows:
            vec = bytes_to_vec(r.embedding_blob, r.embedding_dim)
            if vec is None and r.embedding_json:
                vec = embedding_from_json(r.embedding_json)
            if vec is not None:
                yield vec, r

    def find_relevant(self, query: str, *, max_results: int = 5) -> list[MemoryEntry]:
        try:
            query_vec = encode(query)
        except Exception:
            log.exception("query encode failed")
            query_vec = None

        if query_vec is not None:
            vecs: list[np.ndarray] = []
            entries: list[MemoryEntry] = []
            for vec, entry in self._iter_vectors(limit=_CANDIDATE_LIMIT):
                vecs.append(vec)
                entries.append(entry)
            if vecs:
                matrix = np.stack(vecs)
                sims = np.clip(matrix @ query_vec, -1.0, 1.0)
                importance = np.asarray([e.importance for e in entries], dtype=np.float32)
                scores = sims + importance * 0.3
                order = np.argsort(-scores)[:max_results]
                return [entries[i] for i in order]

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
