"""add append-only per-result posting approvals

Revision ID: 0017_posting_approvals
Revises: 0016_review_consensus
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_posting_approvals"
down_revision = "0016_review_consensus"
branch_labels = None
depends_on = None

def upgrade() -> None:
    status = sa.Enum("ACTIVE", "CONSUMED", "INVALIDATED", "EXPIRED", "SUPERSEDED", name="postingapprovalstatus", native_enum=False)
    cohort = sa.Enum("MAINTAINER", "INDEPENDENT_ENGINEER", name="reviewercohort", native_enum=False)
    classification = sa.Enum("BEHAVIOR_GAP_CONFIRMED", "NEEDS_INFO", "WONT_REPRO", "NOT_A_BUG", "DUPLICATE", name="classification", native_enum=False)
    op.create_table("posting_approvals", sa.Column("id", sa.String(36), primary_key=True), sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id"), nullable=False), sa.Column("review_packet_id", sa.String(36), sa.ForeignKey("review_packets.id"), nullable=False), sa.Column("packet_hash", sa.String(64), nullable=False), sa.Column("packet_version", sa.Integer(), nullable=False), sa.Column("consensus_snapshot_id", sa.String(36), sa.ForeignKey("review_consensus_snapshots.id")), sa.Column("consensus_snapshot_hash", sa.String(64)), sa.Column("consensus_algorithm_version", sa.String(32)), sa.Column("comment_body_hash", sa.String(64), nullable=False), sa.Column("classification", classification, nullable=False), sa.Column("comment_type", sa.String(64), nullable=False), sa.Column("policy_version", sa.String(32), nullable=False), sa.Column("reviewer_external_id", sa.String(128), nullable=False), sa.Column("reviewer_cohort", cohort, nullable=False), sa.Column("reviewer_role", sa.String(32), nullable=False), sa.Column("status", status, nullable=False), sa.Column("rationale", sa.Text()), sa.Column("approval_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_posting_approvals_investigation_id", "posting_approvals", ["investigation_id"])
    op.create_index("ix_posting_approvals_review_packet_id", "posting_approvals", ["review_packet_id"])
    op.create_table("posting_approval_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("approval_id", sa.String(36), sa.ForeignKey("posting_approvals.id"), nullable=False), sa.Column("event_type", sa.String(32), nullable=False), sa.Column("payload_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_posting_approval_events_approval_id", "posting_approval_events", ["approval_id"])
    # SQLite cannot add a foreign-key constraint with ALTER TABLE. The
    # application-level immutable approval ID remains sufficient for this
    # historical job reference, matching existing SQLite migration practice.
    op.add_column("webhook_jobs", sa.Column("posting_approval_id", sa.String(36)))
    op.add_column("webhook_jobs", sa.Column("posting_approval_hash", sa.String(64)))

def downgrade() -> None:
    op.drop_column("webhook_jobs", "posting_approval_hash")
    op.drop_column("webhook_jobs", "posting_approval_id")
    op.drop_table("posting_approval_events")
    op.drop_table("posting_approvals")
