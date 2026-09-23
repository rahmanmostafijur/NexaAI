from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_MESSAGE_CHARS = 4000


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    conversation_id: uuid.UUID | None = None

    @field_validator("message")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = "".join(ch for ch in value if ch in "\n\t" or ch.isprintable()).strip()
        if not cleaned:
            raise ValueError("Message must not be empty")
        return cleaned


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    details: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message: MessageOut
