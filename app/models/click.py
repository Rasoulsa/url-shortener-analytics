from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.link import Link


class Click(Base):
    """
    Time-series fact table for Phase 3 click analytics.

    Each row represents one successful redirect/click event.

    Captured/enriched data:
      - precise visit timestamp
      - anonymized IP address
      - raw User-Agent
      - parsed browser
      - parsed OS
      - device type
      - referrer
      - GeoIP country/city

    Privacy note:
      Raw IP addresses are never stored.
      ip_anonymized stores a privacy-safe representation.

      IPv4 example:
        203.0.113.45 -> 203.0.113.0

    Index strategy:
      ix_clicks_link_id_clicked_at:
        Historical time-series/date-range queries per link.

      ix_clicks_clicked_at:
        Global historical queries and future partitioning support.

      ix_clicks_link_id_country:
        Country breakdown per link.

      ix_clicks_link_id_browser:
        Browser breakdown per link.

      ix_clicks_link_id_device_type:
        Device breakdown per link.

    Production note:
      For very high click volume, consider monthly RANGE partitioning
      by clicked_at.
    """

    __tablename__ = "clicks"

    __table_args__ = (
        Index("ix_clicks_link_id_clicked_at", "link_id", "clicked_at"),
        Index("ix_clicks_clicked_at", "clicked_at"),
        Index("ix_clicks_link_id_country", "link_id", "country"),
        Index("ix_clicks_link_id_browser", "link_id", "browser"),
        Index("ix_clicks_link_id_device_type", "link_id", "device_type"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    link_id: Mapped[int] = mapped_column(
        ForeignKey("links.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Privacy: raw IP is never stored. Store anonymized IP only.
    # IPv4 example: 203.0.113.45 -> 203.0.113.0
    # IPv6 should also be stored only after anonymization/truncation.
    ip_anonymized: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # Raw User-Agent captured from request headers.
    # Parsed fields below are populated by the Phase 3 analytics task.
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

    # GeoIP enrichment. These fields may be NULL when GeoIP DB is unavailable.
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

    def __repr__(self) -> str:
        return f"<Click id={self.id} link_id={self.link_id} at={self.clicked_at}>"
