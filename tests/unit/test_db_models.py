import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import (
    Base, Student, KnowledgePoint, Question, ErrorRecord,
    StudentMastery, Plan, ChatSession, Message, MemoryEntry, MoodLog,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_can_insert_student(db_session):
    s = Student(name="小明", grade=12, school="清华附中", pin_hash="hash123")
    db_session.add(s)
    db_session.commit()
    assert s.id is not None
    assert s.created_at is not None


def test_can_create_knowledge_point_with_prereqs(db_session):
    parent = KnowledgePoint(subject="math", chapter="函数与导数", point_name="导数定义", difficulty=3)
    db_session.add(parent)
    db_session.flush()
    child = KnowledgePoint(
        subject="math", chapter="函数与导数", point_name="切线方程",
        difficulty=4, prereq_ids=[parent.id],
    )
    db_session.add(child)
    db_session.commit()
    assert child.prereq_ids == [parent.id]


def test_can_link_error_record_to_student_and_question(db_session):
    s = Student(name="小明", grade=12, pin_hash="h")
    q = Question(subject="math", stem="求 f(x)=x^2 在 x=1 的切线方程", answer="y=2x-1", knowledge_point_ids=[])
    db_session.add_all([s, q])
    db_session.flush()
    e = ErrorRecord(
        student_id=s.id, question_id=q.id,
        user_answer="y=2x", error_type="concept",
        knowledge_point_ids=[], mastery_level=0.3, source="photo",
    )
    db_session.add(e)
    db_session.commit()
    assert e.id is not None
    assert e.student.id == s.id
    assert e.question.id == q.id


def test_message_belongs_to_session(db_session):
    s = Student(name="小明", grade=12, pin_hash="h")
    db_session.add(s)
    db_session.flush()
    chat = ChatSession(student_id=s.id, status="active")
    db_session.add(chat)
    db_session.flush()
    m = Message(session_id=chat.id, role="user", agent=None, content="Hello", metadata_json={})
    db_session.add(m)
    db_session.commit()
    assert m.session.id == chat.id


def test_memory_entry_stores_typed_payload(db_session):
    s = Student(name="小明", grade=12, pin_hash="h")
    db_session.add(s)
    db_session.flush()
    me = MemoryEntry(
        student_id=s.id, type="weakness", key="导数:切线方程",
        content="多次在切线方程问题上选错斜率", importance=0.8,
    )
    db_session.add(me)
    db_session.commit()
    assert me.id is not None


def test_student_mastery_tracks_counts(db_session):
    s = Student(name="小明", grade=12, pin_hash="h")
    kp = KnowledgePoint(subject="math", chapter="函数", point_name="切线方程", difficulty=3)
    db_session.add_all([s, kp])
    db_session.flush()
    sm = StudentMastery(student_id=s.id, knowledge_point_id=kp.id, mastery_score=0.6, correct_count=3, wrong_count=2)
    db_session.add(sm)
    db_session.commit()
    assert sm.mastery_score == 0.6
    assert sm.correct_count == 3


def test_mood_log_stores_red_flag(db_session):
    s = Student(name="小明", grade=12, pin_hash="h")
    db_session.add(s)
    db_session.flush()
    ml = MoodLog(student_id=s.id, self_score=2, topics=["anxiety"], summary="pressure", red_flag=True)
    db_session.add(ml)
    db_session.commit()
    assert ml.red_flag is True
