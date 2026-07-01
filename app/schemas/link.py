from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class LinkCreate(BaseModel):
    long_url: HttpUrl = Field(
        description="Destination URL to shorten",
    )
    custom_alias: str | None = Field(
        default=None,
        min_length=3,
        max_length=32,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description=(
            "Optional custom short code (3–32 chars, alphanumeric / hyphens / underscores). "
            "Returns 409 if already taken."
        ),
    )
    expires_at: datetime | None = Field(
        default=None,
        description=(
            "Optional expiry timestamp (ISO-8601 UTC). "
            "After this time the redirect returns 410 Gone."
        ),
    )
    password: str | None = Field(
        default=None,
        description="Optional password. Redirect endpoint requires X-Link-Password header.",
    )
    is_permanent: bool = Field(
        default=False,
        description=(
            "`true` → 301 redirect (browser-cached, analytics fires once). "
            "`false` → 302 redirect (re-fires analytics on every visit)."
        ),
    )
    webhook_url: HttpUrl | None = Field(
        default=None,
        description="URL to POST when the click threshold is reached.",
    )
    webhook_threshold: int | None = Field(
        default=None,
        gt=0,
        description="Click count that triggers the webhook POST.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Basic short link",
                    "value": {
                        "long_url": "https://github.com/your-org/your-repo",
                    },
                },
                {
                    "summary": "Custom alias with expiry",
                    "value": {
                        "long_url": "https://example.com/very/long/path",
                        "custom_alias": "launch-day",
                        "expires_at": "2026-12-31T23:59:59Z",
                    },
                },
                {
                    "summary": "Permanent redirect with webhook",
                    "value": {
                        "long_url": "https://example.com/product",
                        "is_permanent": True,
                        "webhook_url": "https://hooks.example.com/clicks",
                        "webhook_threshold": 1000,
                    },
                },
            ]
        }
    }


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
    expires_at: datetime | None = Field(
        default=None,
        description="New expiry timestamp. Set to null to remove expiry.",
    )
    is_permanent: bool | None = Field(
        default=None,
        description="Change redirect type: true=301, false=302.",
    )
    webhook_url: HttpUrl | None = Field(
        default=None,
        description="New webhook URL. Set to null to remove.",
    )
    webhook_threshold: int | None = Field(
        default=None,
        gt=0,
        description="New webhook threshold click count.",
    )
