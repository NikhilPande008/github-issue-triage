"""add durable GitHub webhook jobs and comment audit fields

Revision ID: 0009_webhook_jobs
Revises: 0008_behavior_gap_verdict
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_webhook_jobs"
down_revision = "0008_behavior_gap_verdict"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("delivery_id", sa.String(255), nullable=False, unique=True),
        sa.Column("repository", sa.String(255), nullable=False),
        sa.Column("issue_number", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("status", sa.Enum("QUEUED", "RUNNING", "COMPLETED", "FAILED", name="webhookjobstatus"), nullable=False),
        sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id"), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("comment_status", sa.Enum("PENDING", "PROPOSED", "POSTED", "SKIPPED", "FAILED", name="commentstatus"), nullable=False),
        sa.Column("comment_reason", sa.Text(), nullable=True),
        sa.Column("proposed_comment_body", sa.Text(), nullable=True),
        sa.Column("posted_comment_body", sa.Text(), nullable=True),
        sa.Column("github_comment_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_webhook_jobs_delivery_id", "webhook_jobs", ["delivery_id"])


def downgrade() -> None:
    op.drop_index("ix_webhook_jobs_delivery_id", table_name="webhook_jobs")
    op.drop_table("webhook_jobs")
