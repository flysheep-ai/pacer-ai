from __future__ import annotations
from pathlib import Path
from sqlalchemy import create_engine
from fastapi.testclient import TestClient
from pacer.api.server import create_app
from pacer.db.models import Base


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_serves_legacy_web_when_no_dist(monkeypatch, tmp_path):
    legacy = tmp_path / "web"
    _write(legacy / "index.html", "<!doctype html>LEGACY")
    _write(legacy / "static" / "app.css", "/* css */")
    monkeypatch.setattr("pacer.api.server.LEGACY_WEB_DIR", legacy)
    monkeypatch.setattr("pacer.api.server.NEXT_DIST_DIR", tmp_path / "doesnotexist")
    client = TestClient(create_app(database_url="sqlite:///:memory:"))
    r = client.get("/")
    assert r.status_code == 200
    assert "LEGACY" in r.text


def test_serves_web_next_dist_when_present(monkeypatch, tmp_path):
    legacy = tmp_path / "web"
    _write(legacy / "index.html", "<!doctype html>LEGACY")
    next_dist = tmp_path / "dist"
    _write(next_dist / "index.html", "<!doctype html>NEXT")
    _write(next_dist / "assets" / "main.js", "console.log(1)")
    monkeypatch.setattr("pacer.api.server.LEGACY_WEB_DIR", legacy)
    monkeypatch.setattr("pacer.api.server.NEXT_DIST_DIR", next_dist)
    client = TestClient(create_app(database_url="sqlite:///:memory:"))
    r = client.get("/")
    assert r.status_code == 200
    assert "NEXT" in r.text
    r2 = client.get("/assets/main.js")
    assert r2.status_code == 200
    assert "console.log" in r2.text


def test_spa_fallback_returns_index_for_unknown_path(monkeypatch, tmp_path):
    next_dist = tmp_path / "dist"
    _write(next_dist / "index.html", "<!doctype html>NEXT")
    monkeypatch.setattr("pacer.api.server.LEGACY_WEB_DIR", tmp_path / "nope")
    monkeypatch.setattr("pacer.api.server.NEXT_DIST_DIR", next_dist)
    client = TestClient(create_app(database_url="sqlite:///:memory:"))
    r = client.get("/chat/42")
    assert r.status_code == 200
    assert "NEXT" in r.text


def test_api_routes_not_shadowed_by_spa_fallback(monkeypatch, tmp_path):
    next_dist = tmp_path / "dist"
    _write(next_dist / "index.html", "<!doctype html>NEXT")
    monkeypatch.setattr("pacer.api.server.LEGACY_WEB_DIR", tmp_path / "nope")
    monkeypatch.setattr("pacer.api.server.NEXT_DIST_DIR", next_dist)
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    Base.metadata.create_all(create_engine(db_url))
    client = TestClient(create_app(database_url=db_url))
    r = client.post("/auth/login", json={"student_id": 999999, "pin": "wrong"})
    assert r.status_code in (401, 422)
    assert "NEXT" not in r.text
