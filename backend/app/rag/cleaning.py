"""Text normalisation applied before chunking."""

from __future__ import annotations

import re
import unicodedata

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​﻿]")
_SPACES = re.compile(r"[ \t   ]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")
_HYPHEN_BREAK = re.compile(r"([A-Za-z])-\n([a-z])")
_MARKDOWN_EMPHASIS = re.compile(r"(\*\*|__)(.+?)\1")


def clean_text(text: str, *, markdown: bool = False) -> str:
    """Normalise Unicode (NFC, important for Bengali), whitespace and artefacts."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    if markdown:
        text = _MARKDOWN_EMPHASIS.sub(r"\2", text)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return _MANY_NEWLINES.sub("\n\n", text).strip()
