"""add immutable semantic review packets

Revision ID: 0014_review_packets
Revises: 0013_duplicate_similarity
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_review_packets"
down_revision = "0013_duplicate_similarity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("investigations", sa.Column("review_packet_status", sa.String(32), nullable=True))
    op.add_column("investigations", sa.Column("review_packet_reason", sa.Text(), nullable=True))
    op.create_table("review_packets", sa.Column("id", sa.String(36), primary_key=True), sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id"), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("schema_version", sa.String(32), nullable=False), sa.Column("snapshot_json", sa.Text(), nullable=False), sa.Column("integrity_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("investigation_id", "version", name="uq_review_packet_investigation_version"))
    op.create_index("ix_review_packets_investigation_id", "review_packets", ["investigation_id"])


def downgrade() -> None:
    op.drop_table("review_packets")
    op.drop_column("investigations", "review_packet_reason")
    op.drop_column("investigations", "review_packet_status")
