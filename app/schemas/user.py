from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters")


class UserOut(BaseModel):
    id: int
    email: str
    api_key: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserLogin(BaseModel):
    """Login via email+password OR api_key. Provide one of the two paths."""

    email: EmailStr | None = None
    password: str | None = None
    api_key: str | None = None

    @model_validator(mode="after")
    def _check_credentials(self) -> "UserLogin":
        if self.api_key:
            return self
        if self.email and self.password:
            return self
        raise ValueError("Provide either 'api_key', or both 'email' and 'password'.")
