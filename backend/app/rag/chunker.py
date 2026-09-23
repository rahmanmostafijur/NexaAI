"""Section-aware chunking.

Rules:
* A chunk never spans two pages (so page citations stay accurate) and never
  spans two sections (so each chunk is about one topic).
* Paragraphs are packed up to `chunk_size` characters; a paragraph that is
  too long is split on sentence boundaries (including the Bengali danda "।").
* Consecutive chunks of the same section overlap by up to `overlap` characters,
  taken from whole sentences, so facts at a boundary are not lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.rag.extractors import PageText

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+")
_TERMINAL_PUNCTUATION = tuple(".,:;!?।)")
_SMALL_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "vs",
    "with",
    "per",
    "not",
}


@dataclass(frozen=True)
class Chunk:
    index: int
    content: str
    page: int | None
    section: str | None

    @property
    def token_estimate(self) -> int:
        return max(1, len(self.content) // 4)


@dataclass(frozen=True)
class _Block:
    text: str
    page: int | None
    section: str | None


def looks_like_heading(line: str) -> bool:
    """Heuristic heading detection for PDFs and plain text (no markup available)."""
    stripped = line.strip()
    if not stripped or len(stripped) > 70 or stripped.endswith(_TERMINAL_PUNCTUATION):
        return False
    if stripped.startswith(("-", "•", "|", "*", "(")) or (
        stripped[0].isdigit() and ". " not in stripped[:4]
    ):
        return False
    words = stripped.split()
    if len(words) > 8:
        return False
    if not stripped[0].isascii():
        return len(words) <= 6  # Bengali has no letter case; rely on shortness
    # Headings are Title Case ("Warranty Coverage by Category"); wrapped sentence
    # fragments ("Employees get 20 days of annual") are not.
    significant = [w for w in words if w.lower() not in _SMALL_WORDS and w[0].isalpha()]
    if not significant or not stripped[0].isupper():
        return False
    capitalised = sum(1 for w in significant if w[0].isupper())
    return capitalised / len(significant) >= 0.6


def merge_wrapped_lines(lines: list[str]) -> list[str]:
    """Re-join lines that a PDF layout wrapped mid-sentence ("Fitness" + "machine motors...")."""
    merged: list[str] = []
    for line in lines:
        stripped = line.strip()
        previous = merged[-1] if merged else ""
        continues = (
            previous
            and not previous.endswith(_TERMINAL_PUNCTUATION)
            and not looks_like_heading(previous)
            and (stripped[:1].islower() or (stripped[:1].isdigit() and stripped[1:3] != ". "))
        )
        if continues:
            merged[-1] = f"{previous} {stripped}"
        else:
            merged.append(stripped)
    return merged


def _blocks(pages: list[PageText], heading_style: str, title: str | None) -> list[_Block]:
    blocks: list[_Block] = []
    section: str | None = None
    for page in pages:
        if heading_style == "markdown":
            units = [u for u in re.split(r"\n\s*\n", page.text) if u.strip()]
        else:
            units = merge_wrapped_lines([u for u in page.text.split("\n") if u.strip()])
        for unit in units:
            first_line, _, rest = unit.strip().partition("\n")
            heading = None
            if heading_style == "markdown":
                match = _MD_HEADING.match(first_line)
                if match:
                    heading = match.group(2).strip()
            elif looks_like_heading(first_line) and not rest:
                heading = first_line.strip()
            if heading is not None:
                if title and heading.lower() == title.lower() and section is None:
                    continue  # document title, not a section
                section = heading[:300]
                if rest.strip():
                    blocks.append(_Block(rest.strip(), page.page, section))
                continue
            blocks.append(_Block(unit.strip(), page.page, section))
    return blocks


def _split_long(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_SPLIT.split(text):
        while len(sentence) > limit:  # a single enormous "sentence"
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > limit:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def _overlap_tail(text: str, overlap: int) -> str:
    if overlap <= 0:
        return ""
    sentences = _SENTENCE_SPLIT.split(text)
    tail = ""
    for sentence in reversed(sentences):
        candidate = f"{sentence} {tail}".strip()
        if len(candidate) > overlap:
            break
        tail = candidate
    return tail


def chunk_document(
    pages: list[PageText],
    *,
    chunk_size: int,
    overlap: int,
    heading_style: str = "markdown",
    title: str | None = None,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer: list[str] = []
    key: tuple[int | None, str | None] | None = None

    def flush(carry_overlap: bool) -> None:
        nonlocal buffer
        if not buffer or key is None:
            return
        content = "\n".join(buffer).strip()
        if content:
            chunks.append(Chunk(len(chunks), content, key[0], key[1]))
        tail = _overlap_tail(content, overlap) if carry_overlap else ""
        buffer = [tail] if tail and tail != content else []

    for block in _blocks(pages, heading_style, title):
        block_key = (block.page, block.section)
        if block_key != key:
            flush(carry_overlap=False)
            buffer = []
            key = block_key
        for piece in _split_long(block.text, chunk_size):
            current_len = sum(len(part) + 1 for part in buffer)
            if buffer and current_len + len(piece) > chunk_size:
                flush(carry_overlap=True)
            buffer.append(piece)
    flush(carry_overlap=False)
    return chunks
