# Import all models so Alembic discovers them via Base.metadata
from app.models.click import Click
from app.models.link import Link
from app.models.user import User

__all__ = ["User", "Link", "Click"]
