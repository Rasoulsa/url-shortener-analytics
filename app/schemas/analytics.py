from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AnalyticsDimension = Literal[
    "country",
    "city",
    "browser",
    "os",
    "device_type",
    "referrer",
]


class AnalyticsMeta(BaseModel):
    from_: datetime = Field(alias="from")
    to: datetime
    short_code: str | None = None


class AnalyticsOverview(BaseModel):
    short_code: str
    original_url: str | None = None
    stored_click_count: int
    event_count: int
    unique_countries: int
    unique_browsers: int
    first_click_at: datetime | None = None
    last_click_at: datetime | None = None


class TimeSeriesPoint(BaseModel):
    date: str
    clicks: int


class BreakdownItem(BaseModel):
    label: str
    clicks: int
    percentage: float
