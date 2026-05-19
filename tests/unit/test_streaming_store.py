import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student
from pacer.session.store import SessionStore


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = Session(engine)
    s = Student(name="X", grade=12, pin_hash="h")
    sess.add(s)
    sess.commit()
    yield sess
    sess.close()


def test_create_empty_assistant_and_finalize(db_session):
    store = SessionStore(db_session)
    chat = store.create_session(student_id=1)
    msg = store.create_empty_assistant(chat.id, agent="subject_teacher")
    assert msg.status == "streaming"
    assert msg.content == ""

    store.append_content_to_message(msg.id, "hello")
    store.append_content_to_message(msg.id, " world")
    store.finalize_message(msg.id, content="hello world", status="done")

    # Re-fetch
    from pacer.db.models import Message

    final = db_session.get(Message, msg.id)
    assert final.content == "hello world"
    assert final.status == "done"


def test_create_empty_assistant_with_metadata(db_session):
    store = SessionStore(db_session)
    chat = store.create_session(student_id=1)
    msg = store.create_empty_assistant(chat.id, agent="homeroom", metadata={"route": "homeroom"})
    assert msg.metadata_json == {"route": "homeroom"}
