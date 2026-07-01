"""add phase 3 analytics stats indexes

Revision ID: 9d3b77fc4dc7
Revises: 86ea9159fecb
Create Date: 2026-07-01 00:51:16.482118

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '9d3b77fc4dc7'
down_revision: str | None = '86ea9159fecb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clicks_link_id_clicked_at "
        "ON clicks (link_id, clicked_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clicks_clicked_at "
        "ON clicks (clicked_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clicks_link_country_clicked_at "
        "ON clicks (link_id, country, clicked_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clicks_link_browser_clicked_at "
        "ON clicks (link_id, browser, clicked_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clicks_link_referrer_clicked_at "
        "ON clicks (link_id, referrer, clicked_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clicks_link_device_clicked_at "
        "ON clicks (link_id, device_type, clicked_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_clicks_link_device_clicked_at")
    op.execute("DROP INDEX IF EXISTS ix_clicks_link_referrer_clicked_at")
    op.execute("DROP INDEX IF EXISTS ix_clicks_link_browser_clicked_at")
    op.execute("DROP INDEX IF EXISTS ix_clicks_link_country_clicked_at")
    op.execute("DROP INDEX IF EXISTS ix_clicks_clicked_at")
    op.execute("DROP INDEX IF EXISTS ix_clicks_link_id_clicked_at")
