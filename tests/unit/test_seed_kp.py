import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, KnowledgePoint
from scripts.seed_knowledge_points import (
    stable_id, seed_from_yaml, upsert_knowledge_point,
)


def test_stable_id_is_deterministic():
    a = stable_id("math", "集合的基本概念")
    b = stable_id("math", "集合的基本概念")
    assert a == b
    assert isinstance(a, int)
    assert 0 < a < 2**31


def test_stable_id_differs_by_subject():
    assert stable_id("math", "导数") != stable_id("physics", "导数")


def test_upsert_creates_new_row(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        upsert_knowledge_point(s, kp_name="集合", subject="math",
                               chapter="集合与函数", difficulty=2, exam_freq=3)
        s.commit()
    with Session(engine) as s:
        kp = s.query(KnowledgePoint).filter_by(subject="math", point_name="集合").first()
        assert kp is not None
        assert kp.chapter == "集合与函数"
        assert kp.difficulty == 2
        assert kp.exam_freq == 3


def test_upsert_updates_existing_row(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        upsert_knowledge_point(s, kp_name="集合", subject="math",
                               chapter="旧章节", difficulty=1, exam_freq=1)
        s.commit()
        first_id = s.query(KnowledgePoint).filter_by(
            subject="math", point_name="集合").first().id
    with Session(engine) as s:
        upsert_knowledge_point(s, kp_name="集合", subject="math",
                               chapter="集合与函数", difficulty=3, exam_freq=5)
        s.commit()
        kp = s.query(KnowledgePoint).filter_by(
            subject="math", point_name="集合").first()
        assert kp.id == first_id
        assert kp.difficulty == 3
        assert kp.exam_freq == 5


def test_seed_from_yaml_resolves_prereqs(tmp_path, monkeypatch, tmpdir):
    import yaml
    yaml_text = """
math:
  - name: 集合
    chapter: 集合
    difficulty: 1
    prereqs: []
    exam_freq: 1
  - name: 函数
    chapter: 函数
    difficulty: 2
    prereqs: [集合]
    exam_freq: 3
"""
    yaml_path = tmpdir / "test_kp.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_from_yaml(s, str(yaml_path))
        s.commit()
    with Session(engine) as s:
        kps = s.query(KnowledgePoint).filter_by(subject="math").all()
        assert len(kps) == 2
        fn = next(kp for kp in kps if kp.point_name == "函数")
        assert len(fn.prereq_ids) == 1
        jihe = next(kp for kp in kps if kp.point_name == "集合")
        assert fn.prereq_ids[0] == jihe.id
