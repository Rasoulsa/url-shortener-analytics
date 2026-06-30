from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.link import Link


class Click(Base):
    """
    Time-series fact table for Phase 3 click analytics.

    Each row represents one redirect/click event.

    Captured/enriched data:
      - precise visit timestamp
      - anonymized IP address
      - raw User-Agent
      - parsed browser
      - parsed OS
      - device type
      - referrer
      - GeoIP country/city

    Index strategy:
      (link_id, clicked_at)  -> historical time-series/date-range queries
      (link_id, country)     -> country breakdown per link
      (link_id, browser)     -> browser breakdown per link
      (link_id, device_type) -> device breakdown per link

    Production note:
      For very high click volume, RANGE partition by clicked_at monthly.
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

    # Privacy: raw IP is never stored. Store anonymized IP only.
    # IPv4 example: 203.0.113.45 -> 203.0.113.0
    ip_anonymized: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # Raw User-Agent captured from request headers.
    # Parsed fields below are populated by the Phase 3 Celery analytics task.
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    browser: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    os: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    device_type: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    # Referrer captured from Referer/Referrer request header.
    referrer: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # GeoIP enrichment, populated by Phase 3 Celery analytics task.
    country: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    city: Mapped[str | None] = mapped_column(
        String(128),
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
        Index("ix_clicks_link_device_type", "link_id", "device_type"),
    )

    def __repr__(self) -> str:
        return f"<Click id={self.id} link_id={self.link_id} at={self.clicked_at}>"
