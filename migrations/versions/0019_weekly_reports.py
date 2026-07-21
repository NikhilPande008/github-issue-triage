"""add reason tags and immutable pilot weekly reports
Revision ID: 0019_weekly_reports
Revises: 0018_review_telemetry
"""
import sqlalchemy as sa
from alembic import op
revision="0019_weekly_reports"; down_revision="0018_review_telemetry"; branch_labels=None; depends_on=None
def upgrade():
    op.add_column("review_assessments",sa.Column("reason_tags_json",sa.Text(),nullable=False,server_default="[]"))
    op.create_table("pilot_weekly_reports",sa.Column("id",sa.String(36),primary_key=True),sa.Column("repository",sa.String(255),nullable=False),sa.Column("period_start",sa.DateTime(timezone=True),nullable=False),sa.Column("period_end",sa.DateTime(timezone=True),nullable=False),sa.Column("schema_version",sa.String(32),nullable=False),sa.Column("report_json",sa.Text(),nullable=False),sa.Column("report_hash",sa.String(64),nullable=False),sa.Column("generated_at",sa.DateTime(timezone=True),nullable=False),sa.Column("source_cutoff_at",sa.DateTime(timezone=True),nullable=False)); op.create_index("ix_pilot_weekly_reports_repository","pilot_weekly_reports",["repository"])
def downgrade(): op.drop_table("pilot_weekly_reports"); op.drop_column("review_assessments","reason_tags_json")
