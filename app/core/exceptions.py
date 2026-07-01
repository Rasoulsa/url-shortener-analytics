"""Application exception hierarchy.

Routers raise these instead of HTTPException so a single set of handlers
in main.py renders every error into the canonical envelope.
"""

from __future__ import annotations


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Resource not found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Resource already exists."


class GoneError(AppError):
    status_code = 410
    code = "gone"
    message = "This resource has expired."


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Authentication required."


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "You do not have access to this resource."


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests."
