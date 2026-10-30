#!/usr/bin/env python
"""Crop every numbered display equation from a PDF in one pass, tightly.

Why this exists: the generic asset extractor guesses display-math bands from
page geometry and often pulls in neighbouring prose or a second equation, so a
reader ends up re-cropping by hand and re-reading the image several times.
This script instead anchors on the equation NUMBER line ("(7)") and expands
upward only across rows that look like math, which yields a tight, clean crop
on the first try.

Usage:
    python crop_display_equations.py <pdf> <figures_dir> [--dpi 320] [--dry-run]

Output names follow the note convention: eq_<number>_p<page>.png
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pymupdf

# "(7)" at the right margin, or a bare trailing "7"
EQ_NUMBER_RE = re.compile(r"\(\s*(\d{1,3})\s*\)\s*$")
# Characters that mean "this row is prose / a caption", not math
PROSE_HINTS = ("Figure ", "Table ", "Published as", "where ", "and ", "the ", "is ", "we ")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def rows_of_page(page: pymupdf.Page) -> list[dict]:
    """Return one entry per visual text row with its bbox and text."""
    rows = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            rows.append({"rect": pymupdf.Rect(x0, y0, x1, y1), "text": text})
    rows.sort(key=lambda r: (round(r["rect"].y0, 1), r["rect"].x0))
    return rows


def looks_like_math(text: str) -> bool:
    """Heuristic: equation rows carry operators, sub/superscript glyphs, or symbols."""
    if CJK_RE.search(text):
        return False
    if any(hint in text for hint in PROSE_HINTS):
        return False
    stripped = EQ_NUMBER_RE.sub("", text).strip()
    if not stripped:
        return False
    # The limits of a sum/fraction are often bare fragments on their own row:
    # "N", "X", "2 PN", "i=1 Mi", "m". A short row qualifies only when it also
    # carries a math glyph or a bare index pattern �?plain lowercase words are
    # prose fragments such as "ularity alignment" and must not be swallowed.
    tokens = stripped.split()
    if len(stripped) <= 12 and len(tokens) <= 2:
        if re.search(r"[=^_∑∏∫]", stripped):
            return True
        # "2 PN" / "Mi" / "N" / "X": digits plus uppercase glyph runs are the
        # misaligned operators and limits that PyMuPDF emits on their own row.
        if re.fullmatch(r"[\d\s]*[A-Z][A-Za-z]?", stripped):
            return True
        if len(stripped) <= 3 and not re.search(r"[a-z]{2,}", stripped):
            return True
    # Long wordy rows are prose, not math
    words = re.findall(r"[A-Za-z]{4,}", stripped)
    if len(words) >= 4 and not re.search(r"[=+\-*/^_]", stripped):
        return False
    math_signals = len(re.findall(r"[=+\-*/^_∑∏∫≤≥≈⊤∥σσταβγλΔθϕ]", stripped))
    return math_signals >= 2 or bool(re.search(r"[=]", stripped))


def find_equations(page: pymupdf.Page) -> list[tuple[str, pymupdf.Rect]]:
    """Group math rows that terminate in an equation number into one rect."""
    rows = rows_of_page(page)

    # Cluster vertically-adjacent math rows into equation blocks first, then
    # attach each numbered row to the block it sits in. Blocking by proximity
    # (not by glyph identity) is what keeps a fraction's denominator limits,
    # which PyMuPDF emits as separated one-token rows, inside the same block.
    math_rows = [r for r in rows if looks_like_math(r["text"]) or EQ_NUMBER_RE.search(r["text"])]
    blocks: list[list[dict]] = []
    for item in math_rows:
        if blocks:
            previous = blocks[-1][-1]
            if item["rect"].y0 - previous["rect"].y1 <= 26:
                blocks[-1].append(item)
                continue
        blocks.append([item])

    results = []
    for block in blocks:
        numbered = [r for r in block if EQ_NUMBER_RE.search(r["text"])]
        if not numbered:
            continue
        number = EQ_NUMBER_RE.search(numbered[0]["text"]).group(1)
        rect = pymupdf.Rect(block[0]["rect"])
        for item in block[1:]:
            rect |= item["rect"]
        # 4pt breathing room, never more: keeps neighbouring prose out
        rect = pymupdf.Rect(rect.x0 - 4, rect.y0 - 7, rect.x1 + 4, rect.y1 + 4)
        results.append((number, rect))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("figures_dir", type=Path)
    parser.add_argument("--dpi", type=int, default=320)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    args.figures_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(args.pdf)
    scale = args.dpi / 72.0
    produced = []
    for page_index in range(doc.page_count):
        page = doc[page_index]
        for number, rect in find_equations(page):
            name = f"eq_{number}_p{page_index + 1}.png"
            if not args.dry_run:
                pix = page.get_pixmap(
                    matrix=pymupdf.Matrix(scale, scale), clip=rect, alpha=False
                )
                pix.save(str(args.figures_dir / name))
            produced.append({
                "file": name,
                "page": page_index + 1,
                "number": number,
                "rect": [round(v, 1) for v in rect],
            })

    print(json.dumps({"ok": True, "count": len(produced), "equations": produced},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
