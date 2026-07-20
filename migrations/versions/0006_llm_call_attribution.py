"""add LLM call attribution provenance

Revision ID: 0006_llm_call_attribution
Revises: 0005_investigation_issue_title
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_llm_call_attribution"
down_revision = "0005_investigation_issue_title"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("llm_calls") as batch_op:
        batch_op.add_column(sa.Column("attempt_number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("provider", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("pricing_version", sa.String(length=64), nullable=True))
        batch_op.alter_column("cost_usd", existing_type=sa.Numeric(precision=12, scale=6), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("llm_calls") as batch_op:
        batch_op.alter_column("cost_usd", existing_type=sa.Numeric(precision=12, scale=6), nullable=False)
        batch_op.drop_column("pricing_version")
        batch_op.drop_column("provider")
        batch_op.drop_column("attempt_number")
