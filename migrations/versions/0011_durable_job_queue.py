"""durable leases, retries, priorities, and queue source

Revision ID: 0011_durable_job_queue
Revises: 0010_investigation_test_runner
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_durable_job_queue"
down_revision = "0010_investigation_test_runner"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("webhook_jobs") as batch:
        batch.alter_column("status", existing_type=sa.Enum("QUEUED", "RUNNING", "COMPLETED", "FAILED", name="webhookjobstatus"), type_=sa.Enum("QUEUED", "RUNNING", "SUCCEEDED", "COMPLETED", "FAILED", "RETRY_SCHEDULED", "CANCELLED", "DEAD_LETTER", name="webhookjobstatus"), existing_nullable=False)
        batch.add_column(sa.Column("source", sa.Enum("WEBHOOK", "BATCH", "MANUAL", name="jobsource"), nullable=False, server_default="WEBHOOK"))
        batch.add_column(sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
        batch.add_column(sa.Column("lease_owner", sa.String(255), nullable=True))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("next_eligible_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_webhook_jobs_claim", "webhook_jobs", ["status", "next_eligible_at", "priority"])

def downgrade() -> None:
    op.drop_index("ix_webhook_jobs_claim", table_name="webhook_jobs")
    with op.batch_alter_table("webhook_jobs") as batch:
        batch.alter_column("status", existing_type=sa.Enum("QUEUED", "RUNNING", "SUCCEEDED", "COMPLETED", "FAILED", "RETRY_SCHEDULED", "CANCELLED", "DEAD_LETTER", name="webhookjobstatus"), type_=sa.Enum("QUEUED", "RUNNING", "COMPLETED", "FAILED", name="webhookjobstatus"), existing_nullable=False)
        batch.drop_column("next_eligible_at")
        batch.drop_column("lease_expires_at")
        batch.drop_column("lease_owner")
        batch.drop_column("max_attempts")
        batch.drop_column("attempt_count")
        batch.drop_column("priority")
        batch.drop_column("source")
