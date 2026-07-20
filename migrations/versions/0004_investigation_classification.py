"""persist investigation classification metadata

Revision ID: 0004_investigation_classification
Revises: 0003_investigation_validation
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_investigation_classification"
down_revision = "0003_investigation_validation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.add_column(sa.Column("classification_model", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("classification_completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("investigations") as batch_op:
        batch_op.drop_column("classification_completed_at")
        batch_op.drop_column("classification_model")
