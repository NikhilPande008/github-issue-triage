"""add advisory repository-local similarity records

Revision ID: 0013_duplicate_similarity
Revises: 0012_budget_controls
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_duplicate_similarity"
down_revision = "0012_budget_controls"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("similarity_documents", sa.Column("id", sa.String(36), primary_key=True), sa.Column("investigation_id", sa.String(36), sa.ForeignKey("investigations.id"), unique=True, nullable=False), sa.Column("repository", sa.String(255), nullable=False), sa.Column("document_version", sa.String(32), nullable=False), sa.Column("canonical_text", sa.Text(), nullable=False), sa.Column("checksum", sa.String(64), nullable=False), sa.Column("embedding_provider", sa.String(64)), sa.Column("embedding_model", sa.String(128)), sa.Column("embedding_vector", sa.Text()), sa.Column("embedding_status", sa.String(32), nullable=False), sa.Column("error_reason", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_similarity_documents_repository", "similarity_documents", ["repository"])
    op.create_table("duplicate_candidates", sa.Column("id", sa.String(36), primary_key=True), sa.Column("source_investigation_id", sa.String(36), sa.ForeignKey("investigations.id"), nullable=False), sa.Column("candidate_investigation_id", sa.String(36), sa.ForeignKey("investigations.id"), nullable=False), sa.Column("repository", sa.String(255), nullable=False), sa.Column("similarity_score", sa.Numeric(6,4), nullable=False), sa.Column("scoring_version", sa.String(32), nullable=False), sa.Column("matched_signals", sa.Text(), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("stale", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("source_investigation_id", "candidate_investigation_id", name="uq_duplicate_candidate_pair"))
    op.create_index("ix_duplicate_candidates_repository", "duplicate_candidates", ["repository"])

def downgrade() -> None:
    op.drop_table("duplicate_candidates"); op.drop_table("similarity_documents")
