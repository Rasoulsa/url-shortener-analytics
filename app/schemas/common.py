from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """A single structured error.

    `code`    — stable machine-readable identifier (e.g. "not_found").
    `message` — human-readable description.
    `field`   — optional; for validation errors, the offending field path.
    """

    code: str
    message: str
    field: str | None = None


class Meta(BaseModel):
    """Response metadata.

    Carries pagination info and any endpoint-specific metadata
    (analytics date ranges, counts, etc.). Extra keys are allowed so
    endpoints can attach context without a schema change per endpoint.
    """

    next_cursor: str | None = None
    count: int | None = None

    model_config = {"extra": "allow"}


class Envelope(BaseModel, Generic[T]):  # noqa: UP046
    """
    Consistent API response envelope used on every endpoint.

    Shape:
        {
            "data":   <payload or null>,
            "meta":   <metadata or null>,
            "errors": [ {code, message, field?}, ... ]
        }

    Benefits:
    - Clients always know where data vs errors live.
    - Metadata (pagination, ranges) is always in meta, never in data.
    - Errors are structured objects, not bare strings — clients can
      switch on `code` and surface `field` for form validation.
    """

    data: T | None = None
    meta: Meta | None = None
    errors: list[ErrorDetail] = []


def meta_from(**kwargs: Any) -> Meta:
    """Build a Meta from arbitrary keys (thanks to extra='allow').

    Convenience for endpoints that attach custom metadata, e.g.:
        meta_from(**{"from": start, "to": end, "short_code": code})
    """
    return Meta(**kwargs)
