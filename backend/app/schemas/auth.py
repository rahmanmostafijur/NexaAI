from __future__ import annotations

import re
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str) -> str:
    """Syntactic check only (internal domains such as `.local` must be accepted)."""
    value = value.strip().lower()
    if not _EMAIL.match(value):
        raise ValueError("Enter a valid email address")
    return value


Email = Annotated[str, Field(max_length=320), AfterValidator(_validate_email)]


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=2, max_length=200)

    @field_validator("password")
    @classmethod
    def _strength(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must contain at least one letter and one number")
        return value

    @field_validator("full_name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return " ".join(value.split())


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Literal["admin", "user"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_in: int
    user: UserOut
