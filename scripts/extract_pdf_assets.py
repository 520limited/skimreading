#!/usr/bin/env python
"""Extract page text, render pages, and crop figure/table candidates from a PDF.

This script is intentionally conservative: it never claims semantic correctness by
itself. It creates page maps, page PNGs, figure/table crops, and a manifest that
the agent must inspect before using assets in a note. It also generates a QA
contact sheet so crop quality can be reviewed quickly without manual bookkeeping.
"""

from __future__ import annotations

import argparse
import json
import re
import textwrap
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from math import ceil
from pathlib import Path

import fitz

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional dependency fallback
    Image = None
    ImageDraw = None
    ImageFont = None


CAPTION_RE = re.compile(
    r"(?im)^\s*("
    r"(?:fig(?:ure)?\.?|table|algorithm)\s*[\d]+(?:[-.]\d+)?[a-z]?|"
    r"(?:图|表|算法)\s*[\d]+(?:[-.]\d+)?[a-z]?"
    r")\s*[:：.\-)]?\s*(.+)"
)
EXPERIMENT_SIGNAL_RE = re.compile(
    r"\b(?:experiment|experimental|evaluation|evaluations|result|results|"
    r"performance|benchmark|ablation|accuracy|loss|perplexity|latency|"
    r"retrieval|generalization|comparison|validation|test set|speed)\b",
    re.IGNORECASE,
)
PROSE_REFERENCE_RE = re.compile(
    r"(?i)^(?:fig(?:ure)?\.?|table|algorithm)\s*[\d]+(?:[-.]\d+)?[a-z]?\s+"
    r"(?:shows?|illustrates?|demonstrates?|compares?|presents?|plots?|reports?|ablates?|"
    r"benchmarks?|summarizes?|details?|lists?|provides?|contains?|gives?|uses?|is|are|was|were)\b"
)
SECTION_HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[A-Z])\s+[A-Z][A-Za-z].{0,90}$")
MATH_SIGNAL_RE = re.compile(r"[=<>≤≥≈±×÷√∑∫_\\^]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
DISPLAY_MATH_RE = re.compile(
    r"(?x)"
    r"("
    r"[=<>]\s*|"
    r"\\?[A-Za-z]_\{?[A-Za-z0-9]+\}?|"
    r"[A-Za-z]\([A-Za-z0-9_,\s]+\)|"
    r"[+\-*/]\s*[A-Za-z0-9]|"
    r"\([0-9]{1,2}\)\s*$"
    r")"
)


@dataclass
class Asset:
    path: str
    type: str
    ref: str
    page: int
    caption: str
    rect: list[float]
    confidence: str
    notes: str
    extraction_confidence: str = ""
    crop_quality_score: float = 0.0
    crop_quality_status: str = "unknown"
    qa_flags: list[str] = field(default_factory=list)
    selected_strategy: str = ""
    candidate_count: int = 1
    experiment_candidate: bool = False
    requires_visual_verification: bool = False
    caption_included: bool = False


@dataclass
class CropCandidate:
    rect: fitz.Rect
    confidence: str
    notes: str
    strategy: str


def slug(value: str, limit: int = 42) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return (value or "asset")[:limit].strip("_")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def confidence_rank(value: str) -> int:
    order = {"low": 0, "medium": 1, "high": 2, "verified": 3}
    return order.get(value.lower(), 99)


def is_experimental_figure(caption: str) -> bool:
    """Flag figures that must be classified during synthesis.

    This is intentionally a recall-oriented heuristic. The note author still
    classifies every figure in ``visual_qa.asset_decisions`` before embedding.
    """
    return bool(EXPERIMENT_SIGNAL_RE.search(caption))


def text_blocks(page: fitz.Page) -> list[tuple[fitz.Rect, str]]:
    blocks = []
    for raw in page.get_text("blocks"):
        if len(raw) < 5:
            continue
        rect = fitz.Rect(raw[:4])
        text = clean_text(raw[4])
        if text:
            blocks.append((rect, text))
    return sorted(blocks, key=lambda item: (item[0].y0, item[0].x0))


def is_section_heading(text: str) -> bool:
    return bool(SECTION_HEADING_RE.match(clean_text(text)))


def looks_like_table_text(text: str) -> bool:
    compact = clean_text(text)
    digit_count = sum(char.isdigit() for char in compact)
    if digit_count >= 6:
        return True
    if len(compact) <= 180 and re.search(r"(?i)\b(model|method|metric|dataset|precision|average|ppl|acc|fp\d+)\b", compact):
        return True
    if len(MATH_SIGNAL_RE.findall(compact)) >= 4:
        return True
    # Formula-heavy tables can have few ASCII digits. Treat concise label/math
    # rows as table data unless they read like a normal prose sentence.
    prose_markers = re.compile(r"(?i)\b(we|this|these|our|the|which|that|because|therefore|however)\b")
    return len(compact) <= 300 and not prose_markers.search(compact)


def overlaps_horizontally(first: fitz.Rect, second: fitz.Rect, tolerance: float = 12) -> bool:
    return first.x1 >= second.x0 - tolerance and first.x0 <= second.x1 + tolerance


def table_text_band(
    caption_rect: fitz.Rect,
    blocks: list[tuple[fitz.Rect, str]],
    caption_rects: list[fitz.Rect],
    direction: str,
) -> fitz.Rect | None:
    """Find the contiguous table text immediately above or below its caption."""
    if direction not in {"above", "below"}:
        raise ValueError(f"unsupported direction: {direction}")
    candidates: list[tuple[fitz.Rect, str]] = []
    for rect, text in blocks:
        if not overlaps_horizontally(rect, caption_rect):
            continue
        if any(rect.intersects(other) for other in caption_rects):
            continue
        if direction == "above" and rect.y1 <= caption_rect.y0:
            candidates.append((rect, text))
        elif direction == "below" and rect.y0 >= caption_rect.y1:
            candidates.append((rect, text))

    candidates.sort(key=lambda item: item[0].y1 if direction == "above" else item[0].y0, reverse=direction == "above")
    selected: list[fitz.Rect] = []
    edge = caption_rect.y0 if direction == "above" else caption_rect.y1
    for rect, text in candidates:
        gap = edge - rect.y1 if direction == "above" else rect.y0 - edge
        if gap > 34 or is_section_heading(text):
            break
        if not selected and not looks_like_table_text(text):
            break
        # Once a table has started, ordinary prose immediately after it must
        # not be absorbed merely because it shares the same column.
        if selected and not looks_like_table_text(text):
            break
        selected.append(rect)
        edge = rect.y0 if direction == "above" else rect.y1
    return union_rect(selected)


def table_drawing_band(page: fitz.Page, caption_rect: fitz.Rect, direction: str) -> fitz.Rect | None:
    """Use horizontal table rules to locate a table body without trailing prose."""
    rules: list[fitz.Rect] = []
    for drawing in page.get_drawings():
        raw_rect = drawing.get("rect")
        if not raw_rect:
            continue
        rect = fitz.Rect(raw_rect)
        if rect.width < page.rect.width * 0.15 or rect.height > 6:
            continue
        # A generous horizontal tolerance can pull an adjacent two-column
        # figure or table into this asset. Genuine table rules normally overlap
        # the caption itself, so keep this tolerance deliberately small.
        if not overlaps_horizontally(rect, caption_rect, tolerance=8):
            continue
        if direction == "above" and rect.y1 <= caption_rect.y0 and caption_rect.y0 - rect.y1 <= page.rect.height * 0.36:
            rules.append(rect)
        elif direction == "below" and rect.y0 >= caption_rect.y1 and rect.y0 - caption_rect.y1 <= page.rect.height * 0.36:
            rules.append(rect)
    if not rules:
        return None
    clusters: list[list[fitz.Rect]] = []
    current: list[fitz.Rect] = []
    edge = 0.0
    for rect in sorted(rules, key=lambda item: item.y0):
        if current and rect.y0 > edge + 120:
            clusters.append(current)
            current = []
        current.append(rect)
        edge = max(edge, rect.y1)
    if current:
        clusters.append(current)
    if direction == "above":
        chosen = min(clusters, key=lambda group: abs(caption_rect.y0 - max(rect.y1 for rect in group)))
    else:
        chosen = min(clusters, key=lambda group: abs(min(rect.y0 for rect in group) - caption_rect.y1))
    # Horizontal PDF rules are zero-height rectangles. fitz.Rect.include_rect()
    # treats them as empty, which previously collapsed a multi-rule table to
    # its first line. Build the bounds explicitly so the crop spans the full
    # body between the first and last rules.
    return fitz.Rect(
        min(rect.x0 for rect in chosen),
        min(rect.y0 for rect in chosen),
        max(rect.x1 for rect in chosen),
        max(rect.y1 for rect in chosen),
    )


def assign_table_drawing_bodies(
    page: fitz.Page,
    table_captions: list[fitz.Rect],
) -> dict[tuple[float, float, float, float], fitz.Rect]:
    """Assign horizontal-rule table bodies to captions one-to-one.

    Per-caption nearest-neighbor selection is ambiguous when two tables are
    consecutive. Page-level assignment prevents both captions from claiming
    the same body, while caption blocks split otherwise-nearby rule clusters.
    """
    rules: list[fitz.Rect] = []
    for drawing in page.get_drawings():
        raw_rect = drawing.get("rect")
        if not raw_rect:
            continue
        rect = fitz.Rect(raw_rect)
        if rect.width >= page.rect.width * 0.15 and rect.height <= 6:
            rules.append(rect)

    clusters: list[list[fitz.Rect]] = []
    current: list[fitz.Rect] = []
    edge = 0.0
    for rect in sorted(rules, key=lambda item: item.y0):
        caption_between = any(edge < caption.y0 and caption.y1 < rect.y0 for caption in table_captions)
        if current and (rect.y0 > edge + 68 or caption_between):
            clusters.append(current)
            current = []
        current.append(rect)
        edge = max(edge, rect.y1)
    if current:
        clusters.append(current)

    rule_clusters = [cluster for cluster in clusters if len(cluster) >= 2]

    pairs: list[tuple[float, int, int, fitz.Rect]] = []
    for caption_index, caption in enumerate(table_captions):
        for body_index, cluster in enumerate(rule_clusters):
            matching_rules = [rect for rect in cluster if overlaps_horizontally(rect, caption, tolerance=8)]
            if len(matching_rules) < 2:
                continue
            body = fitz.Rect(
                min(rect.x0 for rect in matching_rules),
                min(rect.y0 for rect in matching_rules),
                max(rect.x1 for rect in matching_rules),
                max(rect.y1 for rect in matching_rules),
            )
            if body.y1 <= caption.y0:
                distance = caption.y0 - body.y1
            elif body.y0 >= caption.y1:
                distance = body.y0 - caption.y1
            else:
                continue
            if distance <= page.rect.height * 0.36:
                pairs.append((distance, caption_index, body_index, body))

    assigned_captions: set[int] = set()
    assigned_bodies: set[int] = set()
    assignments: dict[tuple[float, float, float, float], fitz.Rect] = {}
    for _, caption_index, body_index, body in sorted(pairs, key=lambda item: item[0]):
        if caption_index in assigned_captions or body_index in assigned_bodies:
            continue
        caption = table_captions[caption_index]
        assignments[tuple(caption)] = body
        assigned_captions.add(caption_index)
        assigned_bodies.add(body_index)
    return assignments


def caption_matches(blocks: Iterable[tuple[fitz.Rect, str]]):
    for rect, text in blocks:
        for match in CAPTION_RE.finditer(text):
            ref = clean_text(match.group(1)).replace("Figure", "Fig.")
            caption = clean_text(match.group(0))
            if PROSE_REFERENCE_RE.match(caption):
                continue
            yield rect, ref, caption


def union_rect(rects: list[fitz.Rect]) -> fitz.Rect | None:
    if not rects:
        return None
    out = fitz.Rect(rects[0])
    for rect in rects[1:]:
        out.include_rect(rect)
    return out


def nearest_drawing_cluster(rects: list[fitz.Rect], caption_y: float) -> list[fitz.Rect]:
    """Return the drawing cluster immediately above a caption.

    Pages can contain several plots. A plain union of all drawings above the
    current caption merges an earlier figure into a later one, so we split the
    vertical layout at meaningful gaps and retain only the nearest cluster.
    """
    if not rects:
        return []
    clusters: list[list[fitz.Rect]] = []
    current: list[fitz.Rect] = []
    current_bottom = 0.0
    for rect in sorted(rects, key=lambda item: (item.y0, item.x0)):
        if current and rect.y0 > current_bottom + 36:
            clusters.append(current)
            current = []
            current_bottom = 0.0
        current.append(rect)
        current_bottom = max(current_bottom, rect.y1)
    if current:
        clusters.append(current)
    return min(clusters, key=lambda cluster: abs(caption_y - max(rect.y1 for rect in cluster)))


def crop_rect_for_caption(page: fitz.Page, caption_rect: fitz.Rect) -> tuple[fitz.Rect, str, str]:
    """Return a likely figure/table crop above a caption.

    Most academic figures have captions below the figure. We first look for
    vector drawings above the caption. If that fails, we crop the vertical band
    above the caption and mark the confidence as low.
    """
    page_rect = page.rect
    drawing_rects = []
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if not rect:
            continue
        rect = fitz.Rect(rect)
        if rect.is_empty or rect.get_area() < 80:
            continue
        near_above = rect.y1 <= caption_rect.y0 + 8 and rect.y1 >= caption_rect.y0 - page_rect.height * 0.46
        overlaps_x = rect.x1 >= caption_rect.x0 - 60 and rect.x0 <= caption_rect.x1 + 60
        wide = rect.width > page_rect.width * 0.12
        if near_above and (overlaps_x or wide):
            drawing_rects.append(rect)

    candidate = union_rect(nearest_drawing_cluster(drawing_rects, caption_rect.y0))
    if candidate:
        # Clamp the top edge to the nearest preceding prose/heading boundary.
        # Vector plots sometimes contribute a stray title glyph above their
        # actual body; the old fixed padding then included that remnant.
        preceding_bottoms = [
            rect.y1
            for rect, text in text_blocks(page)
            if rect.y1 < candidate.y0
            and overlaps_horizontally(rect, candidate, tolerance=8)
            and (is_section_heading(text) or len(clean_text(text)) >= 80)
        ]
        top_boundary = max(preceding_bottoms, default=0.0)
        # In two-column layouts, a normal padding can cross into the adjacent
        # column. Keep narrow left/right column figures inside their column.
        narrow_column = candidate.width < page_rect.width * 0.58
        left_pad = 18 if narrow_column else 28
        right_pad = 8 if narrow_column else 28
        candidate.x0 = max(0, candidate.x0 - left_pad)
        candidate.x1 = min(page_rect.width, candidate.x1 + right_pad)
        candidate.y0 = max(top_boundary + 4 if top_boundary else 0, candidate.y0 - 18)
        # Full caption text belongs to the asset. The former min() expression
        # often kept only the first caption line for vector figures.
        candidate.y1 = min(page_rect.height - 18, max(caption_rect.y1 + 4, candidate.y1 + 16))
        if candidate.width > page_rect.width * 0.68 or caption_rect.width > page_rect.width * 0.68:
            candidate.x0 = 0
            candidate.x1 = page_rect.width
        if candidate.height >= page_rect.height * 0.08:
            return candidate, "medium", "crop from vector drawing bounds near caption"

    fallback_height = min(page_rect.height * 0.38, max(140, caption_rect.y0 - 36))
    rect = fitz.Rect(
        max(18, caption_rect.x0 - 24),
        max(18, caption_rect.y0 - fallback_height),
        min(page_rect.width - 18, caption_rect.x1 + 24),
        min(page_rect.height - 18, caption_rect.y1 + 4),
    )
    if rect.width < page_rect.width * 0.45:
        rect.x0 = 36
        rect.x1 = page_rect.width - 36
    return rect, "low", "fallback crop above caption; inspect before use"


def crop_rect_for_table_caption(page: fitz.Page, caption_rect: fitz.Rect) -> tuple[fitz.Rect, str, str]:
    """Return a likely table crop around a caption.

    Chinese theses and many reports put table captions above the table, so table
    crops should start at the caption and extend downward. If the caption is near
    the bottom of a page, fall back to the generic above-caption crop.
    """
    page_rect = page.rect
    if caption_rect.y1 > page_rect.height * 0.78:
        return crop_rect_for_caption(page, caption_rect)

    below_height = min(page_rect.height * 0.38, page_rect.height - caption_rect.y1 - 18)
    rect = fitz.Rect(
        18,
        max(18, caption_rect.y0 - 10),
        page_rect.width - 18,
        min(page_rect.height - 18, caption_rect.y1 + max(170, below_height)),
    )
    return rect, "low", "table crop from caption-down band; inspect before use"


def above_caption_band(page: fitz.Page, caption_rect: fitz.Rect, scale: float, full_width: bool = False) -> fitz.Rect:
    page_rect = page.rect
    height = min(page_rect.height * scale, max(140, caption_rect.y0 - 24))
    x0 = 18 if full_width else max(18, caption_rect.x0 - 36)
    x1 = page_rect.width - 18 if full_width else min(page_rect.width - 18, caption_rect.x1 + 36)
    if x1 - x0 < page_rect.width * 0.45:
        x0 = 36
        x1 = page_rect.width - 36
    return fitz.Rect(x0, max(18, caption_rect.y0 - height), x1, min(page_rect.height - 18, caption_rect.y1 + 4))


def below_caption_band(page: fitz.Page, caption_rect: fitz.Rect, scale: float) -> fitz.Rect:
    page_rect = page.rect
    height = min(page_rect.height * scale, page_rect.height - caption_rect.y1 - 18)
    return fitz.Rect(
        18,
        max(18, caption_rect.y0 - 10),
        page_rect.width - 18,
        min(page_rect.height - 18, caption_rect.y1 + max(170, height)),
    )


def crop_candidates_for_caption(
    page: fitz.Page,
    caption_rect: fitz.Rect,
    asset_type: str,
    blocks: list[tuple[fitz.Rect, str]] | None = None,
    caption_rects: list[fitz.Rect] | None = None,
    assigned_table_body: fitz.Rect | None = None,
) -> list[CropCandidate]:
    candidates: list[CropCandidate] = []
    if asset_type == "table":
        blocks = blocks or text_blocks(page)
        caption_rects = caption_rects or [caption_rect]
        if assigned_table_body is not None:
            drawing_body = assigned_table_body
            direction = "above" if drawing_body.y1 <= caption_rect.y0 else "below"
            if drawing_body:
                distance = (
                    caption_rect.y0 - drawing_body.y1
                    if direction == "above"
                    else drawing_body.y0 - caption_rect.y1
                )
                drawing_confidence = "high" if distance <= 24 else "medium" if distance <= 90 else "low"
                complete = union_rect([caption_rect, drawing_body])
                assert complete is not None
                complete.x0 = max(18, min(caption_rect.x0, drawing_body.x0) - 10)
                complete.x1 = min(page.rect.width - 18, max(caption_rect.x1, drawing_body.x1) + 10)
                complete.y0 = max(18, complete.y0 - 8)
                complete.y1 = min(page.rect.height - 18, complete.y1 + 8)
                candidates.append(
                    CropCandidate(
                        complete,
                        drawing_confidence,
                        f"table rules detected {direction} caption; anchor gap={distance:.1f}pt",
                        f"table_drawing_{direction}_complete",
                    )
                )
        for direction in ("above", "below"):
            body = table_text_band(caption_rect, blocks, caption_rects, direction)
            if body and body.height >= 18:
                complete = union_rect([caption_rect, body])
                assert complete is not None
                narrow_column = complete.width < page.rect.width * 0.58
                horizontal_pad = 8 if narrow_column else 18
                complete.x0 = max(18, complete.x0 - horizontal_pad)
                complete.x1 = min(page.rect.width - 18, complete.x1 + horizontal_pad)
                complete.y0 = max(18, complete.y0 - 8)
                complete.y1 = min(page.rect.height - 18, complete.y1 + 8)
                candidates.append(
                    CropCandidate(
                        complete,
                        "high",
                        f"table body detected {direction} caption; includes full caption and contiguous table text",
                        f"table_text_{direction}_complete",
                    )
                )
        rect, confidence, notes = crop_rect_for_table_caption(page, caption_rect)
        candidates.append(CropCandidate(rect, confidence, notes, "table_caption_down_default"))
        candidates.append(CropCandidate(below_caption_band(page, caption_rect, 0.55), "low", "larger table crop from caption-down band", "table_caption_down_large"))
        if caption_rect.y1 > page.rect.height * 0.72:
            candidates.append(CropCandidate(above_caption_band(page, caption_rect, 0.42, True), "low", "table fallback crop above caption", "table_above_fallback"))
        return candidates

    rect, confidence, notes = crop_rect_for_caption(page, caption_rect)
    candidates.append(CropCandidate(rect, confidence, notes, "figure_vector_or_above_default"))
    candidates.append(CropCandidate(above_caption_band(page, caption_rect, 0.42, True), "low", "full-width figure crop above caption", "figure_above_full_width"))
    return candidates


def select_best_candidate(page: fitz.Page, candidates: list[CropCandidate], dpi: int, asset_type: str) -> CropCandidate:
    if not candidates:
        return CropCandidate(page.rect, "low", "no candidate available; full page fallback", "full_page_fallback")
    best = candidates[0]
    best_score = -1.0
    for candidate in candidates:
        score, status, flags = score_crop_rect(page, candidate.rect, dpi)
        # A clean crop is not proof that it depicts the referenced asset. Favor
        # caption-anchored/vector candidates over generic, page-wide fallbacks.
        adjusted = confidence_rank(candidate.confidence) * 10 + score
        if candidate.strategy == "figure_vector_or_above_default":
            adjusted += 2.0
        if candidate.strategy == "figure_above_full_width":
            adjusted -= 0.5
        if candidate.strategy.startswith("table_drawing_"):
            adjusted += 3.0
        area_ratio = candidate.rect.get_area() / max(1.0, page.rect.get_area())
        if asset_type == "figure" and area_ratio > 0.55:
            adjusted -= 0.12
        if status == "recrop":
            adjusted -= 0.25
        if adjusted > best_score:
            best = candidate
            best_score = adjusted
    return best


def save_pix(page: fitz.Page, rect: fitz.Rect, out_path: Path, dpi: int) -> None:
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(out_path)


def score_pil_image(img) -> tuple[float, str, list[str]]:
    width, height = img.size
    gray = img.convert("L")
    gray.thumbnail((360, 360))
    pixels = gray.tobytes()

    flags: list[str] = []
    if width < 120 or height < 80:
        flags.append("too_small")
    white_ratio = sum(1 for value in pixels if value >= 245) / max(1, len(pixels))
    black_ratio = sum(1 for value in pixels if value <= 40) / max(1, len(pixels))
    nonwhite_ratio = 1.0 - white_ratio
    if nonwhite_ratio < 0.015:
        flags.append("mostly_blank")
    if black_ratio > 0.72:
        flags.append("too_dark")

    score = max(0.0, min(1.0, nonwhite_ratio * 3.0))
    if "too_small" in flags or "mostly_blank" in flags:
        status = "recrop"
    elif score >= 0.12:
        status = "pass"
    else:
        status = "warn"
    return round(score, 3), status, flags


def score_crop_rect(page: fitz.Page, rect: fitz.Rect, dpi: int) -> tuple[float, str, list[str]]:
    if Image is None:
        return 0.0, "unknown", ["pillow_unavailable"]
    try:
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    except Exception:
        return 0.0, "recrop", ["preview_unavailable"]
    return score_pil_image(img)


def score_crop_file(path: Path) -> tuple[float, str, list[str]]:
    if Image is None:
        return 0.0, "unknown", ["pillow_unavailable"]
    if not path.exists():
        return 0.0, "recrop", ["missing_file"]
    try:
        with Image.open(path) as img:
            return score_pil_image(img)
    except Exception:
        return 0.0, "recrop", ["preview_unavailable"]


def annotate_asset_quality(note_dir: Path, assets: list[Asset]) -> None:
    for asset in assets:
        asset.extraction_confidence = asset.confidence
        score, status, flags = score_crop_file(note_dir / asset.path)
        asset.crop_quality_score = score
        asset.crop_quality_status = status
        asset.qa_flags = flags


def chunked(items: list[Asset], size: int) -> Iterable[list[Asset]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def build_qa_contact_sheets(figures_dir: Path, assets: list[Asset], max_assets_per_sheet: int = 12) -> list[str]:
    """Create quick visual review sheets from extracted crops.

    The sheets are stored alongside other figure assets so they can be inspected
    later without rerunning extraction. They are not embedded in the Markdown note.
    """
    if Image is None or ImageDraw is None or ImageFont is None or not assets:
        return []

    ordered_assets = sorted(assets, key=lambda asset: (confidence_rank(asset.confidence), asset.page, asset.ref.lower()))
    sheet_paths: list[str] = []
    font = ImageFont.load_default()
    title_font = ImageFont.load_default()
    cols = 3
    tile_w = 360
    tile_h = 300
    margin = 18
    label_h = 78
    header_h = 54

    for idx, chunk in enumerate(chunked(ordered_assets, max_assets_per_sheet), start=1):
        rows = ceil(len(chunk) / cols)
        width = cols * tile_w + (cols + 1) * margin
        height = header_h + rows * (tile_h + label_h + margin) + margin
        sheet = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(sheet)
        draw.text((margin, 12), f"QA contact sheet {idx}", fill=(20, 20, 20), font=title_font)
        draw.text(
            (margin, 30),
            "Low-confidence crops appear first; inspect these before embedding.",
            fill=(90, 90, 90),
            font=font,
        )

        for pos, asset in enumerate(chunk):
            row = pos // cols
            col = pos % cols
            x = margin + col * (tile_w + margin)
            y = header_h + row * (tile_h + label_h + margin)
            tile = Image.new("RGB", (tile_w, tile_h + label_h), "#f6f6f6")
            tile_draw = ImageDraw.Draw(tile)
            image_path = figures_dir.parent / asset.path
            try:
                with Image.open(image_path) as source:
                    preview = source.convert("RGB")
                    preview.thumbnail((tile_w - 20, tile_h - 20))
                    px = (tile_w - preview.width) // 2
                    py = 10 + (tile_h - preview.height - 20) // 2
                    tile.paste(preview, (px, py))
            except Exception:
                tile_draw.rectangle((10, 10, tile_w - 10, tile_h - 10), outline=(180, 50, 50), width=3)
                tile_draw.text((20, 20), "preview unavailable", fill=(180, 50, 50), font=font)

            border_color = {
                "low": (200, 60, 60),
                "medium": (210, 140, 30),
                "high": (50, 120, 70),
                "verified": (40, 90, 160),
            }.get(asset.confidence.lower(), (120, 120, 120))
            tile_draw.rectangle((0, 0, tile_w - 1, tile_h + label_h - 1), outline=border_color, width=4)
            label = textwrap.fill(
                f"{asset.ref} | p.{asset.page} | {asset.confidence} | crop:{asset.crop_quality_status} | exp:{'yes' if asset.experiment_candidate else 'no'}\n{Path(asset.path).name}",
                width=36,
            )
            tile_draw.multiline_text((14, tile_h + 8), label, fill=(35, 35, 35), font=font, spacing=2)
            sheet.paste(tile, (x, y))

        suffix = f"{idx:02d}" if len(ordered_assets) > max_assets_per_sheet else ""
        sheet_name = f"_qa_contact_sheet{('_' + suffix) if suffix else ''}.png"
        sheet_path = figures_dir / sheet_name
        sheet.save(sheet_path)
        sheet_paths.append(f"figures/{sheet_name}")

    return sheet_paths


def extract_text(doc: fitz.Document, out_dir: Path) -> None:
    pages = []
    text_lines = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text")
        pages.append({"page": i, "text": text})
        text_lines.append(f"\n\n===== PAGE {i} =====\n{text}")
    (out_dir / "fulltext_pages.json").write_text(
        json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "fulltext.txt").write_text("".join(text_lines), encoding="utf-8")


def render_pages(doc: fitz.Document, out_dir: Path, dpi: int) -> None:
    page_dir = out_dir / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    for i, page in enumerate(doc, start=1):
        save_pix(page, page.rect, page_dir / f"page_{i:03d}.png", dpi)


def extract_caption_assets(doc: fitz.Document, figures_dir: Path, dpi: int) -> list[Asset]:
    assets: list[Asset] = []
    seen: set[tuple[int, str]] = set()
    for page_no, page in enumerate(doc, start=1):
        blocks = text_blocks(page)
        captions = list(caption_matches(blocks))
        caption_rects = [caption_rect for caption_rect, _, _ in captions]
        table_caption_rects = [
            caption_rect
            for caption_rect, ref, _ in captions
            if ref.lower().startswith("table") or ref.startswith("表")
        ]
        table_body_assignments = assign_table_drawing_bodies(page, table_caption_rects)
        for caption_rect, ref, caption in captions:
            key = (page_no, ref.lower())
            if key in seen:
                continue
            seen.add(key)

            asset_type = "table" if ref.lower().startswith("table") or ref.startswith("表") else "figure"
            candidates = crop_candidates_for_caption(
                page,
                caption_rect,
                asset_type,
                blocks,
                caption_rects,
                table_body_assignments.get(tuple(caption_rect)),
            )
            selected = select_best_candidate(page, candidates, dpi, asset_type)
            crop_rect, confidence, notes = selected.rect, selected.confidence, selected.notes
            filename = f"{asset_type}_{slug(ref)}_p{page_no}.png"
            save_pix(page, crop_rect, figures_dir / filename, dpi)
            assets.append(
                Asset(
                    path=f"figures/{filename}",
                    type=asset_type,
                    ref=ref,
                    page=page_no,
                    caption=caption,
                    rect=[round(v, 2) for v in (crop_rect.x0, crop_rect.y0, crop_rect.x1, crop_rect.y1)],
                    confidence=confidence,
                    notes=notes,
                    selected_strategy=selected.strategy,
                    candidate_count=len(candidates),
                    experiment_candidate=asset_type == "figure" and is_experimental_figure(caption),
                    requires_visual_verification=asset_type == "figure",
                    caption_included=crop_rect.y0 <= caption_rect.y0 + 2 and crop_rect.y1 >= caption_rect.y1 - 2,
                )
            )
    return assets


def extract_formula_candidates(doc: fitz.Document, figures_dir: Path, dpi: int, max_per_page: int) -> list[Asset]:
    assets: list[Asset] = []
    for page_no, page in enumerate(doc, start=1):
        count = 0
        for rect, text in text_blocks(page):
            if count >= max_per_page:
                break
            compact = clean_text(text)
            if len(compact) > 220 or len(compact) < 8:
                continue
            if not DISPLAY_MATH_RE.search(compact):
                continue
            if CAPTION_RE.search(compact):
                continue
            math_signal_count = len(MATH_SIGNAL_RE.findall(compact))
            cjk_count = len(CJK_RE.findall(compact))
            if math_signal_count < 2:
                continue
            if cjk_count > 8:
                continue
            # Prefer centered or equation-numbered short blocks.
            centered = rect.x0 > page.rect.width * 0.12 and rect.x1 < page.rect.width * 0.88
            numbered = bool(re.search(r"\([0-9]{1,2}\)\s*$", compact))
            if not (centered or numbered):
                continue
            crop = fitz.Rect(
                max(18, rect.x0 - 24),
                max(18, rect.y0 - 12),
                min(page.rect.width - 18, rect.x1 + 24),
                min(page.rect.height - 18, rect.y1 + 12),
            )
            filename = f"formula_candidate_{page_no}_{count + 1}.png"
            save_pix(page, crop, figures_dir / filename, dpi)
            confidence = "medium" if math_signal_count >= 4 and cjk_count <= 2 else "low"
            assets.append(
                Asset(
                    path=f"figures/{filename}",
                    type="formula",
                    ref=f"formula candidate {count + 1}",
                    page=page_no,
                    caption=compact[:180],
                    rect=[round(v, 2) for v in (crop.x0, crop.y0, crop.x1, crop.y1)],
                    confidence=confidence,
                    notes=f"formula candidate from display-math heuristic; math_signals={math_signal_count}; cjk_chars={cjk_count}",
                    selected_strategy="formula_display_math_block",
                    candidate_count=1,
                )
            )
            count += 1
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("note_dir", type=Path)
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--keep-pages", action="store_true", help="Keep rendered full-page PNGs under tmp_pages/pages")
    parser.add_argument("--formula-candidates", type=int, default=0, help="Max formula candidates per page")
    args = parser.parse_args()

    if not args.pdf.exists():
        raise SystemExit(f"PDF not found: {args.pdf}")

    figures_dir = args.note_dir / "figures"
    tmp_dir = args.note_dir / "tmp_pages"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(args.pdf)
    extract_text(doc, tmp_dir)
    if args.keep_pages:
        render_pages(doc, tmp_dir, args.dpi)

    assets = extract_caption_assets(doc, figures_dir, args.dpi)
    if args.formula_candidates:
        assets.extend(extract_formula_candidates(doc, figures_dir, args.dpi, args.formula_candidates))

    annotate_asset_quality(args.note_dir, assets)
    qa_contact_sheets = build_qa_contact_sheets(figures_dir, assets)
    low_confidence_assets = [asset for asset in assets if asset.confidence == "low"]

    manifest = {
        "asset_extraction_version": "2.3",
        "pdf": str(args.pdf),
        "total_pages": doc.page_count,
        "dpi": args.dpi,
        "asset_count": len(assets),
        "assets": [asdict(asset) for asset in assets],
        "review_required": bool(low_confidence_assets),
        "review_rule": "v3.0: only assets actually embedded in the Markdown report require a visual_qa.asset_decisions entry; unused extraction candidates need no decision.",
        "qa_contact_sheets": qa_contact_sheets,
        "qa_summary": {
            "low_confidence_count": len(low_confidence_assets),
            "medium_or_better_count": len(assets) - len(low_confidence_assets),
            "contact_sheet_count": len(qa_contact_sheets),
        },
    }
    (args.note_dir / "asset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"asset_count": len(assets), "manifest": str(args.note_dir / "asset_manifest.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
