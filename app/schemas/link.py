from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class LinkCreate(BaseModel):
    long_url: HttpUrl = Field(description="Destination URL to shorten")
    custom_alias: str | None = Field(
        default=None,
        min_length=3,
        max_length=32,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Optional custom short code (alphanumeric, hyphens, underscores)",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Optional expiry (ISO 8601). Returns 410 after this.",
    )
    password: str | None = Field(
        default=None,
        description="Optional password to protect the link",
    )
    is_permanent: bool = Field(
        default=False,
        description="True=301 redirect (browser-cached). False=302 (re-fires analytics).",
    )
    webhook_url: HttpUrl | None = Field(
        default=None,
        description="URL to POST when click threshold is reached (Day 3)",
    )
    webhook_threshold: int | None = Field(
        default=None,
        gt=0,
        description="Click count that triggers the webhook",
    )


class LinkOut(BaseModel):
    short_code: str
    short_url: str
    long_url: str
    click_count: int
    expires_at: datetime | None
    is_permanent: bool
    has_password: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LinkUpdate(BaseModel):
    expires_at: datetime | None = None
    is_permanent: bool | None = None
    webhook_url: HttpUrl | None = None
    webhook_threshold: int | None = Field(default=None, gt=0)
