"""add immutable deterministic review consensus snapshots

Revision ID: 0016_review_consensus
Revises: 0015_review_assessments
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_review_consensus"
down_revision = "0015_review_assessments"
branch_labels = None
depends_on = None

def upgrade() -> None:
    state = sa.Enum("PENDING_REVIEW", "UNANIMOUSLY_ALIGNED", "DISAGREED", "REJECTED_ALIGNMENT", "INSUFFICIENT_CONTEXT", "UNAVAILABLE", name="consensusstate", native_enum=False)
    op.create_table("review_consensus_snapshots", sa.Column("id", sa.String(36), primary_key=True), sa.Column("review_packet_id", sa.String(36), sa.ForeignKey("review_packets.id"), nullable=False), sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id"), nullable=False), sa.Column("packet_hash", sa.String(64), nullable=False), sa.Column("packet_version", sa.Integer(), nullable=False), sa.Column("algorithm_version", sa.String(32), nullable=False), sa.Column("state", state, nullable=False), sa.Column("snapshot_json", sa.Text(), nullable=False), sa.Column("snapshot_hash", sa.String(64), nullable=False), sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_review_consensus_snapshots_review_packet_id", "review_consensus_snapshots", ["review_packet_id"])
    op.create_index("ix_review_consensus_snapshots_investigation_id", "review_consensus_snapshots", ["investigation_id"])

def downgrade() -> None:
    op.drop_table("review_consensus_snapshots")
