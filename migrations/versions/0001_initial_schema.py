"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    investigation_status = sa.Enum("PENDING", "RUNNING", "COMPLETED", "FAILED", name="investigationstatus")
    classification = sa.Enum(
        "REPRODUCED", "NEEDS_INFO", "WONT_REPRO", "NOT_A_BUG", "DUPLICATE", name="classification"
    )
    op.create_table(
        "investigations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("repository", sa.String(length=255), nullable=False),
        sa.Column("issue_number", sa.Integer(), nullable=False),
        sa.Column("status", investigation_status, nullable=False),
        sa.Column("classification", classification, nullable=True),
        sa.Column("revision_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "hypotheses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("investigation_id", sa.String(length=36), sa.ForeignKey("investigations.id"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("revision_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("investigation_id", sa.String(length=36), sa.ForeignKey("investigations.id"), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("investigation_id", sa.String(length=36), sa.ForeignKey("investigations.id"), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_calls")
    op.drop_table("artifacts")
    op.drop_table("hypotheses")
    op.drop_table("investigations")
