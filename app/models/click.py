from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.link import Link


class Click(Base):
    """
    Time-series fact table for click analytics.

    Index strategy:
      (link_id, clicked_at) -> date-range aggregation per link
      (link_id, country)    -> country breakdown per link
      (link_id, browser)    -> browser breakdown per link

    Production note: RANGE partition by clicked_at monthly.
    """

    __tablename__ = "clicks"

    id: Mapped[int] = mapped_column(primary_key=True)

    link_id: Mapped[int] = mapped_column(
        ForeignKey("links.id", ondelete="CASCADE"),
        nullable=False,
    )

    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Privacy: raw IP never stored, anonymized version only
    ip_anonymized: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # GeoIP, populated by Celery worker on Day 3
    country: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    city: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    # User-agent, populated by Celery worker on Day 3
    browser: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    os: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    device_type: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    # Referrer
    referrer: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    link: Mapped[Link] = relationship(
        "Link",
        back_populates="clicks",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_clicks_link_time", "link_id", "clicked_at"),
        Index("ix_clicks_link_country", "link_id", "country"),
        Index("ix_clicks_link_browser", "link_id", "browser"),
    )

    def __repr__(self) -> str:
        return f"<Click id={self.id} link_id={self.link_id} at={self.clicked_at}>"
