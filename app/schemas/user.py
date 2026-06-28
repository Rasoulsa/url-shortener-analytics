from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters")


class UserOut(BaseModel):
    id: int
    email: str
    api_key: str
    created_at: datetime

    model_config = {"from_attributes": True}
