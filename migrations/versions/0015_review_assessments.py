"""add append-only review assessments and audit ledger

Revision ID: 0015_review_assessments
Revises: 0014_review_packets
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_review_assessments"
down_revision = "0014_review_packets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    judgment = sa.Enum("YES", "NO", "UNCERTAIN", "NOT_ENOUGH_CONTEXT", name="assessmentjudgment", native_enum=False)
    cohort = sa.Enum("MAINTAINER", "INDEPENDENT_ENGINEER", name="reviewercohort", native_enum=False)
    confidence = sa.Enum("LOW", "MEDIUM", "HIGH", name="assessmentconfidence", native_enum=False)
    op.create_table("review_assessments", sa.Column("id", sa.String(36), primary_key=True), sa.Column("review_packet_id", sa.String(36), sa.ForeignKey("review_packets.id"), nullable=False), sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id"), nullable=False), sa.Column("packet_hash", sa.String(64), nullable=False), sa.Column("packet_version", sa.Integer(), nullable=False), sa.Column("reviewer_external_id", sa.String(128), nullable=False), sa.Column("reviewer_cohort", cohort, nullable=False), sa.Column("schema_version", sa.String(32), nullable=False), sa.Column("extraction_aligned", judgment, nullable=False), sa.Column("test_aligned", judgment, nullable=False), sa.Column("failure_supports_signal", judgment, nullable=False), sa.Column("public_comment_appropriate", judgment, nullable=False), sa.Column("confidence", confidence, nullable=False), sa.Column("rationale", sa.Text()), sa.Column("supersedes_assessment_id", sa.String(36), sa.ForeignKey("review_assessments.id")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_review_assessments_review_packet_id", "review_assessments", ["review_packet_id"])
    op.create_index("ix_review_assessments_investigation_id", "review_assessments", ["investigation_id"])
    op.create_table("review_assessment_audit", sa.Column("id", sa.String(36), primary_key=True), sa.Column("assessment_id", sa.String(36), sa.ForeignKey("review_assessments.id"), nullable=False, unique=True), sa.Column("reviewer_external_id", sa.String(128), nullable=False), sa.Column("packet_hash", sa.String(64), nullable=False), sa.Column("payload_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("review_assessment_audit")
    op.drop_table("review_assessments")
