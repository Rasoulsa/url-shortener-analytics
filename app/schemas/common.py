from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Meta(BaseModel):
    """Pagination metadata."""

    next_cursor: str | None = None
    count: int | None = None


class Envelope(BaseModel, Generic[T]):  # noqa: UP046
    """
    Consistent API response envelope used on every endpoint.

    Shape:
        {
            "data":   <payload or null>,
            "meta":   <pagination info or null>,
            "errors": []
        }

    Benefits:
    - Clients always know where data vs errors live.
    - Pagination is always in meta, never in data.
    - Easy to extend without breaking clients.
    """

    data: T | None = None
    meta: Meta | None = None
    errors: list[str] = []
