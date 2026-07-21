"""distinguish completed non-confirming investigations from failures

Revision ID: 0022_completed_no_gap_status
Revises: 0021_eligibility_reports
"""

from alembic import op


revision = "0022_completed_no_gap_status"
down_revision = "0021_eligibility_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # The initial PostgreSQL schema used a native enum; SQLite stores the
    # status as text and needs no schema alteration for the longer value.
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE investigationstatus ADD VALUE IF NOT EXISTS 'COMPLETED_NO_GAP'")
    op.execute(
        """
        UPDATE investigations
        SET status = 'COMPLETED_NO_GAP'
        WHERE status = 'FAILED'
          AND classification IN ('NEEDS_INFO', 'WONT_REPRO', 'NOT_A_BUG')
        """
    )


def downgrade() -> None:
    # PostgreSQL enum values cannot safely be removed in-place. Downgrade the
    # data while leaving the now-unused enum value available.
    op.execute("UPDATE investigations SET status = 'FAILED' WHERE status = 'COMPLETED_NO_GAP'")
