"""Citation validation: keep only citations that refer to real, provided sources."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_GROUP = re.compile(r"\[\s*((?:S|DB)\d+(?:\s*[,;]\s*(?:S|DB)\d+)*)\s*\]", re.IGNORECASE)
_SINGLE = re.compile(r"\[(S\d+|DB\d+)\]")
_COMMENTED = re.compile(r"<!--\s*((?:\[[^\]]{1,40}\]\s*)+)-->")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_FULLWIDTH = re.compile(r"【\s*((?:S|DB)\d+)[^】]{0,20}】", re.IGNORECASE)


@dataclass
class CitationCheck:
    text: str
    used: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def validate_citations(text: str, valid_ids: set[str]) -> CitationCheck:
    """Normalise "[S1, S2]" to "[S1][S2]" and drop ids that were never provided."""
    used: list[str] = []
    removed: list[str] = []

    def replace(match: re.Match[str]) -> str:
        ids = [part.strip().upper() for part in re.split(r"[,;]", match.group(1))]
        kept = []
        for source_id in ids:
            if source_id in valid_ids:
                kept.append(f"[{source_id}]")
                if source_id not in used:
                    used.append(source_id)
            else:
                removed.append(source_id)
        return "".join(kept)

    # Some models hide markers in HTML comments ("<!-- [S1] -->"), which the UI never shows.
    text = _COMMENTED.sub(lambda m: m.group(1).strip(), text)
    # ...and some use full-width brackets with suffixes: "【DB1】", "【S1†L3】".
    text = _FULLWIDTH.sub(r"[\1]", text)
    text = _HTML_COMMENT.sub("", text)
    cleaned = _GROUP.sub(replace, text)
    cleaned = re.sub(r"[ \t]+([.,;:!?।])", r"\1", cleaned)
    return CitationCheck(text=cleaned.strip(), used=used, removed=removed)


def strip_citations(text: str) -> str:
    return _SINGLE.sub("", text)
