"""Text extraction for each supported document type.

Every extractor returns a list of `PageText`. PDFs keep real page numbers so
answers can cite "Page 4"; other formats are a single logical page (page=None)
whose sections come from headings.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import DocumentProcessingError

SOURCE_TYPES = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".csv": "csv",
}

_CSV_MAX_ROWS = 5000


@dataclass(frozen=True)
class PageText:
    text: str
    page: int | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    pages: list[PageText]
    source_type: str
    page_count: int | None
    # "markdown": headings are marked with '#'. "plain": headings are guessed.
    heading_style: str


def source_type_for(filename: str) -> str | None:
    return SOURCE_TYPES.get(Path(filename).suffix.lower())


def extract(data: bytes, source_type: str) -> ExtractedDocument:
    try:
        match source_type:
            case "pdf":
                return _extract_pdf(data)
            case "docx":
                return _extract_docx(data)
            case "markdown":
                return ExtractedDocument([PageText(_decode(data))], source_type, None, "markdown")
            case "txt":
                return ExtractedDocument([PageText(_decode(data))], source_type, None, "plain")
            case "csv":
                return _extract_csv(data)
    except DocumentProcessingError:
        raise
    except Exception as exc:
        raise DocumentProcessingError(
            f"Could not read the {source_type.upper()} file. It may be corrupted."
        ) from exc
    raise DocumentProcessingError(f"Unsupported document type: {source_type}")


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentProcessingError("Text files must be UTF-8 encoded.")


def _extract_pdf(data: bytes) -> ExtractedDocument:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise DocumentProcessingError("Encrypted PDFs are not supported.")
    pages = [
        PageText(text=page.extract_text() or "", page=number)
        for number, page in enumerate(reader.pages, start=1)
    ]
    if not any(p.text.strip() for p in pages):
        raise DocumentProcessingError(
            "No text could be extracted from this PDF (it may be a scanned image)."
        )
    return ExtractedDocument(pages, "pdf", len(pages), "plain")


def _extract_docx(data: bytes) -> ExtractedDocument:
    import docx

    document = docx.Document(io.BytesIO(data))
    lines: list[str] = []
    for block in document.element.body.iterchildren():
        tag = block.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = docx.text.paragraph.Paragraph(block, document)
            text = paragraph.text.strip()
            if not text:
                lines.append("")
                continue
            style = (paragraph.style.name if paragraph.style is not None else "").lower()
            if style.startswith("heading") or style == "title":
                # Title -> "#", Heading 1 -> "##", Heading 2 -> "###" ...
                level = int(style[-1]) + 1 if style[-1:].isdigit() else 1
                lines.extend(["", "#" * min(level, 6) + " " + text, ""])
            elif "list" in style:
                lines.append(f"- {text}")
            else:
                lines.extend([text, ""])
        elif tag == "tbl":
            table = docx.table.Table(block, document)
            for row in table.rows:
                lines.append("| " + " | ".join(cell.text.strip() for cell in row.cells) + " |")
            lines.append("")
    return ExtractedDocument([PageText("\n".join(lines))], "docx", None, "markdown")


def _extract_csv(data: bytes) -> ExtractedDocument:
    reader = csv.reader(io.StringIO(_decode(data)))
    rows = list(reader)
    if not rows:
        raise DocumentProcessingError("The CSV file is empty.")
    header, body = rows[0], rows[1 : _CSV_MAX_ROWS + 1]
    lines = [
        "; ".join(f"{h.strip()}: {v.strip()}" for h, v in zip(header, row, strict=False) if v)
        for row in body
    ]
    return ExtractedDocument(
        [PageText("\n\n".join(line for line in lines if line))], "csv", None, "plain"
    )
