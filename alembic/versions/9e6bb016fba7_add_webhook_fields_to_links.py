"""add webhook fields to links

Revision ID: 9e6bb016fba7
Revises: 3583fb2efbfd
Create Date: 2026-07-01
"""

from __future__ import annotations

from alembic import op


revision = "9e6bb016fba7"
down_revision = "3583fb2efbfd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add webhook fields safely.

    webhook_url and webhook_threshold may already exist from earlier work.
    """

    op.execute(
        """
        ALTER TABLE links
        ADD COLUMN IF NOT EXISTS webhook_url VARCHAR(2048)
        """
    )

    op.execute(
        """
        ALTER TABLE links
        ADD COLUMN IF NOT EXISTS webhook_threshold INTEGER
        """
    )

    op.execute(
        """
        ALTER TABLE links
        ADD COLUMN IF NOT EXISTS webhook_fired BOOLEAN NOT NULL DEFAULT false
        """
    )

    op.execute(
        """
        ALTER TABLE links
        ADD COLUMN IF NOT EXISTS webhook_fired_at TIMESTAMP WITH TIME ZONE
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_links_webhook_pending
        ON links (webhook_fired, webhook_threshold)
        """
    )


def downgrade() -> None:
    """Downgrade only fields safely owned by this branch."""

    op.execute("DROP INDEX IF EXISTS ix_links_webhook_pending")
    op.execute("ALTER TABLE links DROP COLUMN IF EXISTS webhook_fired_at")
    op.execute("ALTER TABLE links DROP COLUMN IF EXISTS webhook_fired")
