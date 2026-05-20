"""optimization_pass: session.title, memory embedding_blob, auth_tokens, llm_usage, student lockout

Revision ID: c1a8e2b73d10
Revises: b9de646ac540
Create Date: 2026-05-19 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1a8e2b73d10"
down_revision: Union[str, Sequence[str], None] = "b9de646ac540"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sessions.title — user-editable conversation title
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("title", sa.String(length=60), nullable=True))

    # memory_entries: binary embedding + dimension (keeps json column for backfill)
    with op.batch_alter_table("memory_entries") as batch:
        batch.add_column(sa.Column("embedding_blob", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("embedding_dim", sa.Integer(), nullable=True))

    # Backfill: convert existing embedding_json (list[float]) into the binary
    # form without re-encoding through the model.
    _backfill_embeddings()

    # students: lockout fields + widened pin_hash column for argon2/bcrypt
    with op.batch_alter_table("students") as batch:
        batch.add_column(sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("login_locked_until", sa.DateTime(), nullable=True))
        batch.alter_column("pin_hash", existing_type=sa.String(length=128), type_=sa.String(length=255))

    # Auth tokens persisted in DB (replaces in-memory dict)
    op.create_table(
        "auth_tokens",
        sa.Column("token", sa.String(length=64), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )

    # LLM usage telemetry
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("agent", sa.String(length=30), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("iterations", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def _backfill_embeddings() -> None:
    """Move existing embedding_json (list[float]) into embedding_blob bytes."""
    import json
    import struct

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, embedding_json FROM memory_entries "
        "WHERE embedding_json IS NOT NULL AND embedding_blob IS NULL"
    )).fetchall()
    for row in rows:
        try:
            vec = json.loads(row.embedding_json)
            if not isinstance(vec, list) or not vec:
                continue
            buf = struct.pack(f"<{len(vec)}f", *vec)
            bind.execute(
                sa.text(
                    "UPDATE memory_entries SET embedding_blob = :blob, embedding_dim = :dim WHERE id = :id"
                ),
                {"blob": buf, "dim": len(vec), "id": row.id},
            )
        except (json.JSONDecodeError, struct.error, TypeError, ValueError):
            continue


def downgrade() -> None:
    op.drop_table("llm_usage")
    op.drop_table("auth_tokens")
    with op.batch_alter_table("students") as batch:
        batch.drop_column("login_locked_until")
        batch.drop_column("failed_login_count")
        batch.alter_column("pin_hash", existing_type=sa.String(length=255), type_=sa.String(length=128))
    with op.batch_alter_table("memory_entries") as batch:
        batch.drop_column("embedding_dim")
        batch.drop_column("embedding_blob")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("title")
