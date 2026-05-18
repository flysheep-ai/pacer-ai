import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student
from pacer.session.store import SessionStore


@pytest.fixture
def store():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = Session(engine)
    s = Student(name="X", grade=12, pin_hash="h")
    sess.add(s); sess.commit()
    yield SessionStore(sess), s.id
    sess.close()


def test_create_session_and_append_messages(store):
    s, sid = store
    chat = s.create_session(student_id=sid)
    s.append_message(chat.id, role="user", agent=None, content="Hi")
    s.append_message(chat.id, role="assistant", agent="homeroom", content="Hello!")
    msgs = s.list_messages(chat.id)
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].agent == "homeroom"


def test_history_for_llm_returns_simplified_format(store):
    s, sid = store
    chat = s.create_session(student_id=sid)
    s.append_message(chat.id, role="user", agent=None, content="A")
    s.append_message(chat.id, role="assistant", agent="homeroom", content="B")
    history = s.history_for_llm(chat.id)
    assert history == [
        {"role": "user", "content": "A"},
        {"role": "assistant", "content": "B"},
    ]
