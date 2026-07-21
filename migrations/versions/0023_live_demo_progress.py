"""add bounded live-demo job progress

Revision ID: 0023_live_demo_progress
Revises: 0022_completed_no_gap_status
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_live_demo_progress"
down_revision = "0022_completed_no_gap_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("webhook_jobs") as batch_op:
        batch_op.add_column(sa.Column("progress_stage", sa.String(length=48), nullable=True))
        batch_op.add_column(sa.Column("progress_detail", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("webhook_jobs") as batch_op:
        batch_op.drop_column("progress_detail")
        batch_op.drop_column("progress_stage")
