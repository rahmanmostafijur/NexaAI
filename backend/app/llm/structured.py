"""Structured (JSON) output from an LLM, validated with Pydantic."""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, ValidationError

from app.core.errors import LLMUnavailableError
from app.llm.base import ChatMessage, LLMProvider

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class StructuredOutputError(LLMUnavailableError):
    code = "llm_invalid_output"


def extract_json_object(text: str) -> dict:
    """Parse the first JSON object in `text`, tolerating code fences and prose."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(cleaned[start : index + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(value, dict):
                        return value
                    break
        start = cleaned.find("{", start + 1)
    raise ValueError("No JSON object found in model output")


async def complete_structured[T: BaseModel](
    llm: LLMProvider,
    messages: list[ChatMessage],
    schema: type[T],
    *,
    max_tokens: int | None = None,
    retries: int = 1,
) -> T:
    """Ask for JSON matching `schema`; on invalid output, re-ask once with the error."""
    conversation = list(messages)
    last_error = ""
    for _ in range(retries + 1):
        response = await llm.complete(
            conversation, temperature=0.0, max_tokens=max_tokens, json_mode=True
        )
        try:
            return schema.model_validate(extract_json_object(response.text))
        except (ValueError, ValidationError) as exc:
            last_error = str(exc)[:500]
            logger.info("Structured output invalid for %s; retrying", schema.__name__)
            conversation = [
                *messages,
                ChatMessage("assistant", response.text[:2000]),
                ChatMessage(
                    "user",
                    "Your previous reply was not valid JSON for the required schema. "
                    f"Error: {last_error}\nReply again with only the corrected JSON object.",
                ),
            ]
    raise StructuredOutputError(
        f"The language model did not return valid structured output ({schema.__name__})."
    )
