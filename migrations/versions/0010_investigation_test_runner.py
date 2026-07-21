"""record deterministic test runner on investigations

Revision ID: 0010_investigation_test_runner
Revises: 0009_webhook_jobs
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_investigation_test_runner"
down_revision = "0009_webhook_jobs"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("investigations") as batch:
        batch.add_column(sa.Column("test_runner", sa.String(32), nullable=False, server_default="pytest"))

def downgrade() -> None:
    with op.batch_alter_table("investigations") as batch:
        batch.drop_column("test_runner")
