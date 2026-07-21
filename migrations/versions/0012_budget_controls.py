"""add attributable budget and unpriced Codex resource fields

Revision ID: 0012_budget_controls
Revises: 0011_durable_job_queue
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_budget_controls"
down_revision = "0011_durable_job_queue"
branch_labels = None
depends_on = None

def upgrade() -> None:
    status = sa.Enum("AVAILABLE", "RESERVED", "EXCEEDED", "UNBUDGETABLE", name="budgetstatus")
    with op.batch_alter_table("investigations") as batch:
        batch.add_column(sa.Column("tracked_openai_cost_usd", sa.Numeric(12, 6), nullable=True))
        batch.add_column(sa.Column("reserved_openai_cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("codex_invocation_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("codex_wall_seconds", sa.Numeric(12, 3), nullable=False, server_default="0"))
        batch.add_column(sa.Column("codex_wall_cap_seconds", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("budget_status", status, nullable=False, server_default="AVAILABLE"))
        batch.add_column(sa.Column("budget_reason", sa.Text(), nullable=True))
    with op.batch_alter_table("webhook_jobs") as batch:
        batch.add_column(sa.Column("budget_status", status, nullable=False, server_default="AVAILABLE"))
        batch.add_column(sa.Column("budget_reason", sa.Text(), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table("webhook_jobs") as batch:
        batch.drop_column("budget_reason"); batch.drop_column("budget_status")
    with op.batch_alter_table("investigations") as batch:
        batch.drop_column("budget_reason"); batch.drop_column("budget_status"); batch.drop_column("codex_wall_cap_seconds"); batch.drop_column("codex_wall_seconds"); batch.drop_column("codex_invocation_count"); batch.drop_column("reserved_openai_cost_usd"); batch.drop_column("tracked_openai_cost_usd")
