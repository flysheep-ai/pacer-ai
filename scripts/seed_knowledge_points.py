"""Seed knowledge_points from a YAML file. Idempotent — re-running upserts by stable id.

Usage:
    python scripts/seed_knowledge_points.py [path/to/knowledge_points.yaml]
"""
from __future__ import annotations
import hashlib
import sys
from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pacer.config import get_settings
from pacer.db.models import KnowledgePoint


def stable_id(subject: str, name: str) -> int:
    """Deterministic 31-bit integer id from (subject, name)."""
    digest = hashlib.md5(f"{subject}|{name}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def upsert_knowledge_point(
    session: Session, *,
    kp_name: str, subject: str, chapter: str,
    difficulty: int, exam_freq: int | None,
    prereq_ids: list[int] | None = None,
) -> KnowledgePoint:
    kp_id = stable_id(subject, kp_name)
    existing = session.get(KnowledgePoint, kp_id)
    if existing is not None:
        existing.point_name = kp_name
        existing.subject = subject
        existing.chapter = chapter
        existing.difficulty = difficulty
        existing.exam_freq = exam_freq
        existing.prereq_ids = prereq_ids or []
        session.flush()
        return existing
    kp = KnowledgePoint(
        id=kp_id, point_name=kp_name, subject=subject,
        chapter=chapter, difficulty=difficulty,
        exam_freq=exam_freq, prereq_ids=prereq_ids or [],
    )
    session.add(kp)
    session.flush()
    return kp


def seed_from_yaml(session: Session, yaml_path: str) -> int:
    """Upsert all KPs from YAML. Returns count written."""
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    total = 0
    for subject_key, entries in data.items():
        kp_by_name: dict[str, KnowledgePoint] = {}
        for entry in entries:
            name = entry["name"]
            kp = upsert_knowledge_point(
                session, kp_name=name, subject=subject_key,
                chapter=entry.get("chapter", ""),
                difficulty=entry.get("difficulty", 3),
                exam_freq=entry.get("exam_freq"),
            )
            kp_by_name[name] = kp
            total += 1
        # Second pass: resolve prereqs by name → id
        for entry in entries:
            prereq_names = entry.get("prereqs") or []
            if not prereq_names:
                continue
            kp = kp_by_name[entry["name"]]
            resolved = [
                kp_by_name[n].id for n in prereq_names if n in kp_by_name
            ]
            if resolved and resolved != kp.prereq_ids:
                kp.prereq_ids = resolved
                session.flush()
    return total


def main() -> None:
    yaml_path = (
        sys.argv[1] if len(sys.argv) > 1
        else str(Path(__file__).parent.parent / "data" / "knowledge_points.yaml")
    )
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as s:
        n = seed_from_yaml(s, yaml_path)
        s.commit()
        print(f"seeded {n} knowledge point(s)")


if __name__ == "__main__":
    main()
