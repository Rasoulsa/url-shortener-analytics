"""phase3 create clicks table

Revision ID: dbbfe45ea5f3
Revises: 7109f86968a5
Create Date: 2026-07-01 01:09:02.148243

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "dbbfe45ea5f3"
down_revision: str | None = "7109f86968a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clicks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ip_anonymized", sa.String(length=64), nullable=True),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("browser", sa.String(length=64), nullable=True),
        sa.Column("os", sa.String(length=64), nullable=True),
        sa.Column("device_type", sa.String(length=16), nullable=True),
        sa.Column("referrer", sa.String(length=2048), nullable=True),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clicks_link_browser", "clicks", ["link_id", "browser"], unique=False)
    op.create_index("ix_clicks_link_country", "clicks", ["link_id", "country"], unique=False)
    op.create_index("ix_clicks_link_time", "clicks", ["link_id", "clicked_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_clicks_link_time", table_name="clicks")
    op.drop_index("ix_clicks_link_country", table_name="clicks")
    op.drop_index("ix_clicks_link_browser", table_name="clicks")
    op.drop_table("clicks")
