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


class BreakdownItem(BaseModel):
    label: str
    clicks: int
    percentage: float


class TimeSeriesPoint(BaseModel):
    date: str  # ISO date "2026-07-02"
    clicks: int


class TimeseriesOut(BaseModel):
    short_code: str
    period_days: int
    total: int
    points: list[TimeSeriesPoint]


class CountBucket(BaseModel):
    label: str
    count: int


class BreakdownOut(BaseModel):
    short_code: str
    total: int
    items: list[CountBucket]


class CompareSeries(BaseModel):
    short_code: str
    total: int
    points: list[TimeSeriesPoint]


class CompareOut(BaseModel):
    period_days: int
    series: list[CompareSeries]
