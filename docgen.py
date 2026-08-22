"""Convert the AI-generated markdown-ish text into a clean .docx file."""

from __future__ import annotations

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


def _apply_heading(doc, text: str, level: int):
    h = doc.add_heading(text, level=min(level, 3))
    for run in h.runs:
        run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    return h


def markdown_to_docx(markdown_text: str) -> Document:
    """Build a Word document from simple markdown (headings, bullets, text)."""
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        stripped = line.strip()
        # Headings: #, ##, ###
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped.lstrip("#").strip()
            _apply_heading(doc, text, level)
        # Bullets
        elif stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:].strip()
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(text)
        # Numbered-ish lines
        elif stripped[:2].isdigit() and len(stripped) > 2 and stripped[2] in ". )":
            text = stripped[3:].strip()
            p = doc.add_paragraph(style="List Number")
            p.add_run(text)
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.add_run(stripped)

    return doc
