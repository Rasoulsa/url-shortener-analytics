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


def _to_out(link: Link) -> LinkOut:
    """Map Link ORM object → LinkOut schema."""
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


@router.post(
    "",
    response_model=Envelope[LinkOut],
    status_code=status.HTTP_201_CREATED,
    summary="Create a short link",
)
async def create_link(
    payload: LinkCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[LinkOut]:
    # ── Custom alias flow ──────────────────────────────────
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

    # ── Persist ────────────────────────────────────────────
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
        "Returns links newest-first with cursor/keyset pagination. "
        "Pass `cursor` (last `id` from previous page) to get the next page."
    ),
)
async def list_links(
    cursor: int | None = Query(
        default=None,
        description="Return links with id < cursor",
    ),
    limit: int = Query(default=20, ge=1, le=100),
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
