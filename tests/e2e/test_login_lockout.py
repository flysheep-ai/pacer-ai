"""E2E: failed PIN attempts lock the account temporarily."""
from __future__ import annotations
import asyncio
import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.api import deps
from pacer.api.server import create_app
from pacer.db.models import Base, Student


@pytest.mark.asyncio
async def test_login_locks_out_after_max_attempts(tmp_path, monkeypatch):
    monkeypatch.setenv("PACER_LOGIN_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("PACER_LOGIN_LOCKOUT_SECONDS", "1")
    url = f"sqlite:///{tmp_path}/t.db"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.commit()
    app = create_app(database_url=url)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t",
    ) as ac:
        # 3 wrong PINs (max_attempts=3)
        for _ in range(3):
            r = await ac.post("/auth/login", json={"student_id": 1, "pin": "000000"})
            assert r.status_code == 401

        # 4th attempt should be locked (429)
        r = await ac.post("/auth/login", json={"student_id": 1, "pin": "000000"})
        assert r.status_code == 429

        # Wait past lockout (1 second)
        await asyncio.sleep(1.5)

        # Now correct PIN should work
        r = await ac.post("/auth/login", json={"student_id": 1, "pin": "123456"})
        assert r.status_code == 200
        assert "token" in r.json()
