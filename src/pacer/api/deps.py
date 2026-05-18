from __future__ import annotations
import hashlib
import secrets
from collections.abc import Iterator
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine
from pacer.config import get_settings

_engine = None
_SessionLocal: sessionmaker[Session] | None = None
_tokens: dict[str, int] = {}


def init_db(database_url: str | None = None) -> None:
    global _engine, _SessionLocal
    url = database_url or get_settings().database_url
    _engine = create_engine(url, future=True)
    _SessionLocal = sessionmaker(
        bind=_engine, autoflush=False, autocommit=False, future=True,
    )


def get_db() -> Iterator[Session]:
    assert _SessionLocal is not None, "init_db() must be called before requests"
    sess = _SessionLocal()
    try:
        yield sess
    finally:
        sess.close()


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def issue_token(student_id: int) -> str:
    tok = secrets.token_urlsafe(32)
    _tokens[tok] = student_id
    return tok


def current_student_id(authorization: str | None = Header(None)) -> int:
    if authorization and authorization.startswith("Bearer "):
        tok = authorization[len("Bearer "):]
    else:
        raise HTTPException(status_code=401, detail="missing bearer token")
    sid = _tokens.get(tok)
    if sid is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return sid


def optional_student_id(
    authorization: str | None = Header(None),
    token: str | None = None,
) -> int:
    """For SSE connections — supports both header and query param."""
    tok = token
    if not tok and authorization and authorization.startswith("Bearer "):
        tok = authorization[len("Bearer "):]
    if not tok:
        raise HTTPException(status_code=401, detail="missing token")
    sid = _tokens.get(tok)
    if sid is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return sid
