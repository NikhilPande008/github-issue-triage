"""persist investigation issue title

Revision ID: 0005_investigation_issue_title
Revises: 0004_investigation_classification
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_investigation_issue_title"
down_revision = "0004_investigation_classification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.add_column(sa.Column("issue_title", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.drop_column("issue_title")
