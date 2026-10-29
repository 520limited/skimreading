#!/usr/bin/env python
"""Dedicated formula QA for skimreading notes."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from markdown_formula import normalize_formula, validate_markdown_formulas


OBSIDIAN_IMAGE_RE = re.compile(r"!\[\[([^\]]+)\]\]")
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_rel(path: str) -> str:
    return path.replace("\\", "/").strip()


def find_markdown(note_dir: Path, data: dict | None = None) -> Path | None:
    declared = note_dir / data.get("markdown_file", "") if data and data.get("markdown_file") else None
    if declared and declared.exists():
        return declared
    for candidate in sorted(note_dir.glob("*.md")):
        return candidate
    return None


def markdown_images(md_text: str) -> set[str]:
    paths = OBSIDIAN_IMAGE_RE.findall(md_text) + MD_IMAGE_RE.findall(md_text)
    return {normalize_rel(path) for path in paths}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("note_dir", type=Path)
    args = parser.parse_args()

    note_dir = args.note_dir
    note_json = note_dir / "note.json"
    manifest_path = note_dir / "asset_manifest.json"
    errors: list[str] = []
    warnings: list[str] = []

    if not note_json.exists():
        errors.append(f"missing note.json: {note_json}")
        print(json.dumps({"ok": False, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 1

    data = load_json(note_json)
    note_md = find_markdown(note_dir, data)
    if note_md is None:
        errors.append(f"missing markdown note in {note_dir}")
        print(json.dumps({"ok": False, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 1

    md_text = note_md.read_text(encoding="utf-8")
    md_image_set = markdown_images(md_text)
    formula_errors, math_spans = validate_markdown_formulas(md_text)
    errors.extend(formula_errors)
    rendered_formulas = {normalize_formula(span.content) for span in math_spans}

    key_formulas = data.get("results_discussion", {}).get("key_formulas", [])
    for formula in key_formulas:
        ref = formula.get("ref")
        screenshot = formula.get("screenshot")
        if not screenshot:
            errors.append(f"key formula has no screenshot: {ref}")
        elif normalize_rel(screenshot) not in md_image_set:
            errors.append(f"key formula screenshot is not embedded in Markdown: {screenshot}")
        if not str(formula.get("explanation", "")).strip():
            errors.append(f"key formula has no explanation: {ref}")
        latex = str(formula.get("latex", "")).strip()
        confidence = formula.get("transcription_confidence")
        if latex and confidence != "high":
            errors.append(f"formula transcription must be high confidence or omitted: {ref}")
        if latex and normalize_formula(latex) not in rendered_formulas:
            errors.append(f"formula LaTeX is not rendered in Markdown: {ref}")

    embedded_formula_assets = []
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        for asset in manifest.get("assets", []):
            path = normalize_rel(asset.get("path", ""))
            if path not in md_image_set:
                continue
            is_formula = asset.get("type") == "formula" or "formula_candidate" in path
            if not is_formula:
                continue
            embedded_formula_assets.append(path)
            if asset.get("confidence") == "low":
                errors.append(f"low-confidence formula asset is embedded; replace or remove: {path}")
            if asset.get("crop_quality_status") == "recrop":
                errors.append(f"formula crop_quality_status=recrop; replace or remove: {path}")

    ok = not errors
    print(
        json.dumps(
            {
                "ok": ok,
                "markdown": str(note_md),
                "embedded_formula_assets": embedded_formula_assets,
                "mathjax_expression_count": len(math_spans),
                "errors": errors,
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
