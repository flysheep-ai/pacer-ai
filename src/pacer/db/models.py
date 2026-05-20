from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Text, LargeBinary, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    grade: Mapped[int] = mapped_column(Integer)
    school: Mapped[Optional[str]] = mapped_column(String(100))
    target_school: Mapped[Optional[str]] = mapped_column(String(100))
    stream: Mapped[Optional[str]] = mapped_column(String(10))
    pin_hash: Mapped[str] = mapped_column(String(255))
    profile_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    login_locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(20))
    chapter: Mapped[str] = mapped_column(String(100))
    point_name: Mapped[str] = mapped_column(String(100))
    difficulty: Mapped[int] = mapped_column(Integer, default=3)
    prereq_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    exam_freq: Mapped[Optional[int]] = mapped_column(Integer)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(20))
    stem: Mapped[str] = mapped_column(Text)
    options: Mapped[Optional[dict]] = mapped_column(JSON)
    answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    knowledge_point_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    difficulty: Mapped[Optional[int]] = mapped_column(Integer)
    source: Mapped[Optional[str]] = mapped_column(String(100))
    year: Mapped[Optional[int]] = mapped_column(Integer)
    image_url: Mapped[Optional[str]] = mapped_column(String(500))


class ErrorRecord(Base):
    __tablename__ = "error_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    question_id: Mapped[Optional[int]] = mapped_column(ForeignKey("questions.id"))
    user_answer: Mapped[Optional[str]] = mapped_column(Text)
    correct_answer: Mapped[Optional[str]] = mapped_column(Text)
    error_type: Mapped[Optional[str]] = mapped_column(String(50))
    knowledge_point_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    mastery_level: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(20))
    explanation_text: Mapped[Optional[str]] = mapped_column(Text)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    student = relationship("Student")
    question = relationship("Question")


class StudentMastery(Base):
    __tablename__ = "student_mastery"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"))
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    last_practice_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    date: Mapped[datetime] = mapped_column(DateTime)
    type: Mapped[str] = mapped_column(String(20))
    tasks_json: Mapped[list] = mapped_column(JSON, default=list)
    generated_by: Mapped[str] = mapped_column(String(50), default="homeroom")
    feedback: Mapped[Optional[str]] = mapped_column(Text)


class ChatSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    title: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    role: Mapped[str] = mapped_column(String(20))
    agent: Mapped[Optional[str]] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="done", server_default="done")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session = relationship("ChatSession")


class MemoryEntry(Base):
    __tablename__ = "memory_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    type: Mapped[str] = mapped_column(String(30))
    key: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    # JSON-encoded text retained for backwards compat; new writes go to embedding_blob (float32 bytes).
    embedding_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    embedding_dim: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class MoodLog(Base):
    __tablename__ = "mood_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sessions.id"))
    self_score: Mapped[Optional[int]] = mapped_column(Integer)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    red_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PendingEvent(Base):
    __tablename__ = "pending_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    event_type: Mapped[str] = mapped_column(String(50))
    data_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class LLMUsage(Base):
    __tablename__ = "llm_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[Optional[int]] = mapped_column(ForeignKey("students.id"), nullable=True)
    session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    agent: Mapped[Optional[str]] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(80))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    iterations: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
