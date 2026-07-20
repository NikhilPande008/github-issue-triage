"""persist investigation validation result

Revision ID: 0003_investigation_validation
Revises: 0002_llm_call_latency
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_investigation_validation"
down_revision = "0002_llm_call_latency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.add_column(sa.Column("asserts_failure", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("validation_reason", sa.Text(), nullable=True))
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.alter_column("asserts_failure", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.drop_column("validation_reason")
        batch_op.drop_column("asserts_failure")
