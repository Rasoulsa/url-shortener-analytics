"""add phase 3 analytics stats indexes

Revision ID: 3583fb2efbfd
Revises: 9d3b77fc4dc7
Create Date: 2026-07-01 01:00:42.363950

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '3583fb2efbfd'
down_revision: str | None = '9d3b77fc4dc7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
