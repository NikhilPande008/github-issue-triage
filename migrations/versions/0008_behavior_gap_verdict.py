"""rename reproduced verdict to behavior gap confirmed

Revision ID: 0008_behavior_gap_verdict
Revises: 0007_codex_cost_unavailable
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_behavior_gap_verdict"
down_revision = "0007_codex_cost_unavailable"
branch_labels = None
depends_on = None

OLD = "REPRODUCED"
NEW = "BEHAVIOR_GAP_CONFIRMED"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f"ALTER TYPE classification RENAME VALUE '{OLD}' TO '{NEW}'"))
        return
    op.execute(sa.text(f"UPDATE investigations SET classification = '{NEW}' WHERE classification = '{OLD}'"))
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.alter_column(
            "classification",
            existing_type=sa.Enum(OLD, "NEEDS_INFO", "WONT_REPRO", "NOT_A_BUG", "DUPLICATE", name="classification"),
            type_=sa.Enum(NEW, "NEEDS_INFO", "WONT_REPRO", "NOT_A_BUG", "DUPLICATE", name="classification"),
            existing_nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f"ALTER TYPE classification RENAME VALUE '{NEW}' TO '{OLD}'"))
        return
    op.execute(sa.text(f"UPDATE investigations SET classification = '{OLD}' WHERE classification = '{NEW}'"))
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.alter_column(
            "classification",
            existing_type=sa.Enum(NEW, "NEEDS_INFO", "WONT_REPRO", "NOT_A_BUG", "DUPLICATE", name="classification"),
            type_=sa.Enum(OLD, "NEEDS_INFO", "WONT_REPRO", "NOT_A_BUG", "DUPLICATE", name="classification"),
            existing_nullable=True,
        )
