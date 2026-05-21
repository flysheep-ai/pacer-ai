"""One-shot back-fill: add uuid `id` + bool `done` to legacy Plan.tasks_json rows.

Idempotent — running it twice is a no-op on already-tagged tasks.

Usage:
    python scripts/backfill_task_ids.py
"""
from __future__ import annotations
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from pacer.config import get_settings
from pacer.db.models import Plan


def backfill_task_ids(database_url: str | None = None) -> int:
    """Return the number of tasks that received a new id."""
    url = database_url or get_settings().database_url
    engine = create_engine(url)
    fixed = 0
    with Session(engine) as s:
        for p in s.query(Plan).all():
            tasks = list(p.tasks_json or [])
            mutated = False
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                if "id" not in t:
                    t["id"] = str(uuid.uuid4())
                    mutated = True
                    fixed += 1
                if "done" not in t:
                    t["done"] = False
                    mutated = True
            if mutated:
                p.tasks_json = tasks
                flag_modified(p, "tasks_json")
        s.commit()
    return fixed


if __name__ == "__main__":
    print(f"backfilled {backfill_task_ids()} task(s)")
