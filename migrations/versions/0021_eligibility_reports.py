"""add immutable automation measurement eligibility reports
Revision ID: 0021_eligibility_reports
Revises: 0020_corpus_exports
"""
import sqlalchemy as sa
from alembic import op
revision="0021_eligibility_reports";down_revision="0020_corpus_exports";branch_labels=None;depends_on=None
def upgrade():
 state=sa.Enum("NOT_EVALUATED","INSUFFICIENT_SAMPLE","INSUFFICIENT_COVERAGE","FALSE_ALIGNMENT_DETECTED","DISAGREEMENT_PRESENT","PRECISION_BELOW_THRESHOLD","DATA_QUALITY_BLOCKED","MEASUREMENT_ELIGIBLE",name="eligibilitystate",native_enum=False)
 op.create_table("automation_eligibility_policies",sa.Column("id",sa.String(36),primary_key=True),sa.Column("cohort_key",sa.String(128),nullable=False),sa.Column("description",sa.Text(),nullable=False),sa.Column("repositories_json",sa.Text(),nullable=False),sa.Column("predicates_json",sa.Text(),nullable=False),sa.Column("policy_version",sa.String(32),nullable=False),sa.Column("policy_hash",sa.String(64),nullable=False),sa.Column("operator_reference",sa.String(128),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
 op.create_table("eligibility_reports",sa.Column("id",sa.String(36),primary_key=True),sa.Column("policy_id",sa.String(36),sa.ForeignKey("automation_eligibility_policies.id"),nullable=False),sa.Column("policy_hash",sa.String(64),nullable=False),sa.Column("state",state,nullable=False),sa.Column("report_json",sa.Text(),nullable=False),sa.Column("report_hash",sa.String(64),nullable=False),sa.Column("source_cutoff_at",sa.DateTime(timezone=True),nullable=False),sa.Column("operator_reference",sa.String(128),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False));op.create_index("ix_eligibility_reports_policy_id","eligibility_reports",["policy_id"])
def downgrade():op.drop_table("eligibility_reports");op.drop_table("automation_eligibility_policies")
