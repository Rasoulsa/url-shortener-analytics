from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.click import Click
    from app.models.user import User


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Core
    short_code: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        index=True,
        nullable=False,
    )

    long_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    # Ownership
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Access control
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Lifecycle
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # True  -> 301 Permanent redirect
    # False -> 302 Temporary redirect
    is_permanent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Counter, synchronized with Redis through asynchronous workers.
    click_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Webhooks, added in Phase 3.
    webhook_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    webhook_threshold: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    webhook_fired: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner: Mapped[User | None] = relationship(
        "User",
        back_populates="links",
        lazy="selectin",
    )

    clicks: Mapped[list[Click]] = relationship(
        "Click",
        back_populates="link",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Link id={self.id} short_code={self.short_code}>"
