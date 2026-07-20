"""allow standalone llm calls and record latency

Revision ID: 0002_llm_call_latency
Revises: 0001_initial_schema
Create Date: 2026-07-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_llm_call_latency"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("llm_calls") as batch_op:
        batch_op.alter_column("investigation_id", existing_type=sa.String(length=36), nullable=True)
        batch_op.add_column(sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("llm_calls") as batch_op:
        batch_op.alter_column("latency_ms", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("llm_calls") as batch_op:
        batch_op.drop_column("latency_ms")
        batch_op.alter_column("investigation_id", existing_type=sa.String(length=36), nullable=False)
