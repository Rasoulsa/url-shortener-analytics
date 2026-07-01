from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.models.link import Link
from app.models.user import User
from app.schemas.common import Envelope, Meta
from app.schemas.link import LinkCreate, LinkOut, LinkUpdate
from app.services.shortener import generate_unique_code, reserve_code

router = APIRouter(prefix="/api/v1/links", tags=["Links"])

# ── Shared response example fragments ────────────────────────────────────────

_LINK_EXAMPLE = {
    "short_code": "gh3Xk2",
    "short_url": "http://localhost:8001/gh3Xk2",
    "long_url": "https://github.com/your-org/your-repo",
    "click_count": 42,
    "expires_at": None,
    "is_permanent": False,
    "has_password": False,
    "created_at": "2026-07-01T12:00:00Z",
    "updated_at": "2026-07-01T12:00:00Z",
}

_404 = {
    "description": "Link not found",
    "content": {
        "application/json": {
            "example": {
                "data": None,
                "meta": {},
                "errors": [{"code": "not_found", "message": "Link not found"}],
            }
        }
    },
}

_401 = {
    "description": "Missing or invalid API key",
    "content": {
        "application/json": {
            "example": {
                "data": None,
                "meta": {},
                "errors": [
                    {
                        "code": "unauthorized",
                        "message": "API key required. Pass it in the X-API-Key header.",
                    }
                ],
            }
        }
    },
}

_422 = {
    "description": "Validation error",
    "content": {
        "application/json": {
            "example": {
                "data": None,
                "meta": {},
                "errors": [
                    {
                        "code": "validation_error",
                        "message": "Field required",
                        "field": "long_url",
                    }
                ],
            }
        }
    },
}


# ── Helper ────────────────────────────────────────────────────────────────────


def _to_out(link: Link) -> LinkOut:
    return LinkOut(
        short_code=link.short_code,
        short_url=f"{settings.base_url}/{link.short_code}",
        long_url=link.long_url,
        click_count=link.click_count,
        expires_at=link.expires_at,
        is_permanent=link.is_permanent,
        has_password=link.password_hash is not None,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=Envelope[LinkOut],
    status_code=status.HTTP_201_CREATED,
    summary="Create a short link",
    description=(
        "Shortens a URL and returns the new link object. "
        "Supply `custom_alias` to choose your own short code (3–32 alphanumeric chars). "
        "Supply `expires_at` (ISO-8601 UTC) to auto-expire the link — "
        "expired links return **410 Gone**. "
        "Supply `webhook_url` + `webhook_threshold` to receive a POST callback "
        "when the click count crosses the threshold."
    ),
    responses={
        201: {
            "description": "Link created",
            "content": {
                "application/json": {
                    "example": {
                        "data": _LINK_EXAMPLE,
                        "meta": None,
                        "errors": [],
                    }
                }
            },
        },
        401: _401,
        409: {
            "description": "Custom alias already taken",
            "content": {
                "application/json": {
                    "example": {
                        "data": None,
                        "meta": {},
                        "errors": [
                            {
                                "code": "conflict",
                                "message": "Alias 'mylink' is already taken.",
                            }
                        ],
                    }
                }
            },
        },
        422: _422,
    },
)
async def create_link(
    payload: LinkCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[LinkOut]:
    if payload.custom_alias:
        existing = (
            await db.execute(select(Link).where(Link.short_code == payload.custom_alias))
        ).scalar_one_or_none()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Alias '{payload.custom_alias}' is already taken.",
            )
        if not await reserve_code(payload.custom_alias):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Alias '{payload.custom_alias}' is being reserved.",
            )
        code = payload.custom_alias
    else:
        code = await generate_unique_code()

    link = Link(
        short_code=code,
        long_url=str(payload.long_url),
        user_id=user.id,
        expires_at=payload.expires_at,
        is_permanent=payload.is_permanent,
        password_hash=hash_password(payload.password) if payload.password else None,
        webhook_url=str(payload.webhook_url) if payload.webhook_url else None,
        webhook_threshold=payload.webhook_threshold,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    return Envelope(data=_to_out(link))


@router.get(
    "",
    response_model=Envelope[list[LinkOut]],
    summary="List your links",
    description=(
        "Returns the authenticated user's links, **newest first**, "
        "using **cursor / keyset pagination**. "
        "\n\n"
        "**Pagination:** pass `cursor` (the `id` value from `meta.next_cursor` "
        "of the previous response) to fetch the next page. "
        "When `meta.next_cursor` is `null` you have reached the last page."
        "\n\n"
        "| Param | Default | Range |\n"
        "|-------|---------|-------|\n"
        "| `limit` | 20 | 1–100 |\n"
        "| `cursor` | — | opaque integer string |"
    ),
    responses={
        200: {
            "description": "Paginated link list",
            "content": {
                "application/json": {
                    "example": {
                        "data": [_LINK_EXAMPLE],
                        "meta": {"next_cursor": "41", "count": 1},
                        "errors": [],
                    }
                }
            },
        },
        401: _401,
    },
)
async def list_links(
    cursor: int | None = Query(
        default=None,
        description="Return links with id < cursor (opaque — copy from meta.next_cursor)",
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Page size (1–100)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[list[LinkOut]]:
    stmt = select(Link).where(Link.user_id == user.id)
    if cursor:
        stmt = stmt.where(Link.id < cursor)
    stmt = stmt.order_by(Link.id.desc()).limit(limit + 1)

    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = str(rows[-1].id) if has_more and rows else None

    return Envelope(
        data=[_to_out(r) for r in rows],
        meta=Meta(next_cursor=next_cursor, count=len(rows)),
    )


@router.get(
    "/{short_code}",
    response_model=Envelope[LinkOut],
    summary="Get a single link",
    description=(
        "Fetches full details for one of your short links by its short code. "
        "Returns **404** if the code does not exist or belongs to another user."
    ),
    responses={
        200: {
            "description": "Link details",
            "content": {
                "application/json": {
                    "example": {
                        "data": _LINK_EXAMPLE,
                        "meta": None,
                        "errors": [],
                    }
                }
            },
        },
        401: _401,
        404: _404,
    },
)
async def get_link(
    short_code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[LinkOut]:
    link = (
        await db.execute(
            select(Link).where(
                Link.short_code == short_code,
                Link.user_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    return Envelope(data=_to_out(link))


@router.patch(
    "/{short_code}",
    response_model=Envelope[LinkOut],
    summary="Update a link",
    description=(
        "Partially updates a link. All fields are optional — "
        "only the fields you send are changed. "
        "\n\n"
        "**Updatable fields:** `expires_at`, `is_permanent`, "
        "`webhook_url`, `webhook_threshold`."
    ),
    responses={
        200: {
            "description": "Updated link",
            "content": {
                "application/json": {
                    "example": {
                        "data": {**_LINK_EXAMPLE, "is_permanent": True},
                        "meta": None,
                        "errors": [],
                    }
                }
            },
        },
        401: _401,
        404: _404,
        422: _422,
    },
)
async def update_link(
    short_code: str,
    payload: LinkUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[LinkOut]:
    link = (
        await db.execute(
            select(Link).where(
                Link.short_code == short_code,
                Link.user_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(link, field, str(value) if field == "webhook_url" and value else value)

    await db.commit()
    await db.refresh(link)
    return Envelope(data=_to_out(link))


@router.delete(
    "/{short_code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a link",
    description=(
        "Permanently deletes a short link and all its associated analytics. "
        "This action is **irreversible**. Returns **204 No Content** on success."
    ),
    responses={
        204: {"description": "Link deleted"},
        401: _401,
        404: _404,
    },
)
async def delete_link(
    short_code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    link = (
        await db.execute(
            select(Link).where(
                Link.short_code == short_code,
                Link.user_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")

    await db.delete(link)
    await db.commit()
