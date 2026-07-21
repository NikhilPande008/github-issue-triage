"""mark synthetic Codex costs unavailable

Revision ID: 0007_codex_cost_unavailable
Revises: 0006_llm_call_attribution
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_codex_cost_unavailable"
down_revision = "0006_llm_call_attribution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only rows whose provider is Codex, or whose legacy model/purpose tuple is
    # unambiguously Codex investigation telemetry, are safe to convert.
    op.execute(
        sa.text(
            """
            UPDATE llm_calls
            SET cost_usd = NULL
            WHERE cost_usd = 0
              AND (
                provider = 'codex'
                OR (provider IS NULL AND model = 'codex' AND purpose = 'investigation')
              )
            """
        )
    )


def downgrade() -> None:
    # This is the inverse only for the records this migration identified as Codex.
    op.execute(
        sa.text(
            """
            UPDATE llm_calls
            SET cost_usd = 0
            WHERE cost_usd IS NULL
              AND (
                provider = 'codex'
                OR (provider IS NULL AND model = 'codex' AND purpose = 'investigation')
              )
            """
        )
    )
