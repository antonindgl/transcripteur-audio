"""Exports TXT / SRT / PDF."""
from __future__ import annotations

import os
from pathlib import Path

from .transcriber import TranscriptionResult

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FONT_CANDIDATES = [
    *sorted(FONT_DIR.glob("*.ttf")),  # polices déposées par l'utilisateur (prioritaires)
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
]


def to_txt(result: TranscriptionResult) -> bytes:
    return result.text.encode("utf-8")


def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def to_srt(result: TranscriptionResult) -> bytes:
    blocks = [
        f"{i}\n{_ts(s.start)} --> {_ts(s.end)}\n{s.text}\n"
        for i, s in enumerate(result.segments, 1)
    ]
    return "\n".join(blocks).encode("utf-8")


def _latin1(s: str) -> str:
    return s.encode("latin-1", "replace").decode("latin-1")


def _build_pdf(title: str, text: str, font: Path | None):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    if font:
        pdf.add_font("U", "", str(font))
        pdf.set_font("U", size=16)
    else:  # police intégrée : latin-1 uniquement
        pdf.set_font("Helvetica", size=16)
        title, text = _latin1(title), _latin1(text)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font_size(12)
    pdf.ln(4)
    pdf.multi_cell(0, 7, text)
    return pdf


def to_pdf(result: TranscriptionResult, title: str = "Transcription") -> bytes:
    font = next((p for p in _FONT_CANDIDATES if os.path.exists(p)), None)
    try:
        pdf = _build_pdf(title, result.text, font)
    except Exception:
        # Police inadaptée à l'écriture : repli lisible plutôt qu'un échec
        pdf = _build_pdf(title, result.text, None)
    return bytes(pdf.output())
