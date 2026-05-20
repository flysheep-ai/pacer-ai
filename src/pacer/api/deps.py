from __future__ import annotations
import hashlib
import logging
import secrets
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, Header
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pacer.config import get_settings

log = logging.getLogger("pacer.deps")

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


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


# -- PIN hashing -------------------------------------------------------------

def hash_pin(pin: str) -> str:
    """Hash a PIN with bcrypt (cost 10). Returns a self-describing string."""
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("ascii")


def _sha256(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def verify_pin(pin: str, stored_hash: str) -> tuple[bool, bool]:
    """Verify a PIN against a stored hash.

    Returns (ok, needs_upgrade). `needs_upgrade=True` indicates the stored hash
    is the legacy unsalted sha256 form and should be re-hashed on success.
    """
    if not stored_hash:
        return False, False
    if stored_hash.startswith("$2"):
        try:
            ok = bcrypt.checkpw(pin.encode("utf-8"), stored_hash.encode("utf-8"))
            return ok, False
        except ValueError:
            return False, False
    # Legacy: hex sha256, 64 chars.
    ok = secrets.compare_digest(_sha256(pin), stored_hash)
    return ok, ok


# -- Auth tokens (DB-backed, with TTL) --------------------------------------

def _utc_naive_now() -> datetime:
    """SQLAlchemy stores DateTime columns as naive UTC. Use naive for compares."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def issue_token(student_id: int, db: Session | None = None) -> str:
    from pacer.db.models import AuthToken
    settings = get_settings()
    own_session = False
    if db is None:
        assert _SessionLocal is not None
        db = _SessionLocal()
        own_session = True
    try:
        tok = secrets.token_urlsafe(32)
        expires = _utc_naive_now() + timedelta(seconds=settings.token_ttl_seconds)
        db.add(AuthToken(token=tok, student_id=student_id, expires_at=expires))
        db.commit()
        return tok
    finally:
        if own_session:
            db.close()


def _resolve_token(tok: str) -> int:
    from pacer.db.models import AuthToken
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        row = db.get(AuthToken, tok)
        if row is None:
            raise HTTPException(status_code=401, detail="invalid token")
        if row.expires_at < _utc_naive_now():
            db.delete(row)
            db.commit()
            raise HTTPException(status_code=401, detail="token expired")
        return row.student_id
    finally:
        db.close()


def current_student_id(authorization: str | None = Header(None)) -> int:
    if not (authorization and authorization.startswith("Bearer ")):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return _resolve_token(authorization[len("Bearer "):])


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
    return _resolve_token(tok)
