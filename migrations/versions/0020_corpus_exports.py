"""add consented semantic corpus export provenance
Revision ID: 0020_corpus_exports
Revises: 0019_weekly_reports
"""
import sqlalchemy as sa
from alembic import op
revision="0020_corpus_exports"; down_revision="0019_weekly_reports"; branch_labels=None; depends_on=None
def upgrade():
 status=sa.Enum("ACTIVE","REVOKED","EXPIRED",name="corpusconsentstatus",native_enum=False)
 op.create_table("corpus_consents",sa.Column("id",sa.String(36),primary_key=True),sa.Column("repository",sa.String(255),nullable=False),sa.Column("purpose",sa.String(32),nullable=False),sa.Column("status",status,nullable=False),sa.Column("consent_version",sa.String(32),nullable=False),sa.Column("operator_reference",sa.String(128),nullable=False),sa.Column("allowed_data_classes_json",sa.Text(),nullable=False),sa.Column("retention_policy_reference",sa.String(128),nullable=False),sa.Column("effective_at",sa.DateTime(timezone=True),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True)),sa.Column("audit_hash",sa.String(64),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False));op.create_index("ix_corpus_consents_repository","corpus_consents",["repository"])
 op.create_table("corpus_exports",sa.Column("id",sa.String(36),primary_key=True),sa.Column("repositories_json",sa.Text(),nullable=False),sa.Column("consent_provenance_json",sa.Text(),nullable=False),sa.Column("purpose",sa.String(32),nullable=False),sa.Column("schema_version",sa.String(32),nullable=False),sa.Column("source_cutoff_at",sa.DateTime(timezone=True),nullable=False),sa.Column("manifest_json",sa.Text(),nullable=False),sa.Column("manifest_hash",sa.String(64),nullable=False),sa.Column("operator_reference",sa.String(128),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
def downgrade():op.drop_table("corpus_exports");op.drop_table("corpus_consents")
