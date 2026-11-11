#!/usr/bin/env python
"""Validate a skimreading note directory."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    import jsonschema
except Exception:  # pragma: no cover - optional dependency fallback
    jsonschema = None

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None


OBSIDIAN_IMAGE_RE = re.compile(r"!\[\[([^\]]+)\]\]")
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_image(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing image: {path}"]
    if path.stat().st_size < 2048:
        errors.append(f"image too small: {path}")
    if Image is not None:
        with Image.open(path) as img:
            width, height = img.size
        if width < 120 or height < 80:
            errors.append(f"image dimensions too small: {path} ({width}x{height})")
    return errors


def normalize_rel(path: str) -> str:
    return path.replace("\\", "/").strip()


def timestamp_from_folder(name: str) -> str | None:
    compact = re.match(r"^(\d{12})_", name)
    if compact:
        return compact.group(1)
    legacy = re.match(r"^(\d{8})-(\d{4})\d{2}_", name)
    if legacy:
        return f"{legacy.group(1)}{legacy.group(2)}"
    return None


def find_markdown(note_dir: Path, data: dict | None = None) -> tuple[Path | None, list[str]]:
    """Prefer the v1.4 timestamp-only Markdown file, fall back to legacy names."""
    warnings: list[str] = []
    timestamp = (data or {}).get("parse_started_at") or timestamp_from_folder(note_dir.name)
    if timestamp and "-" in timestamp:
        timestamp = timestamp.replace("-", "")[:12]
    preferred = note_dir / f"{timestamp}.md" if timestamp else note_dir / f"{note_dir.name}.md"
    declared = note_dir / (data.get("markdown_file", "")) if data and data.get("markdown_file") else None
    if declared and declared.exists():
        return declared, warnings
    if declared:
        warnings.append(f"declared markdown_file not found: {declared.name}")
    legacy = note_dir / "note.md"
    if preferred.exists():
        return preferred, warnings
    same_name = note_dir / f"{note_dir.name}.md"
    if same_name.exists():
        warnings.append(f"legacy same-name markdown in use; prefer {preferred.name}")
        return same_name, warnings
    if legacy.exists():
        warnings.append(f"legacy markdown filename in use; prefer {preferred.name}")
        return legacy, warnings
    return None, warnings


def manifest_version_at_least(manifest: dict, target: tuple[int, int]) -> bool:
    try:
        major, minor, *_ = (int(part) for part in str(manifest.get("asset_extraction_version", "0.0")).split("."))
        return (major, minor) >= target
    except ValueError:
        return False


def validate_figure_coverage(data: dict, manifest: dict, md_image_set: set[str]) -> tuple[list[str], list[str]]:
    """Validate only the assets actually used in the note.

    v3.0 fast mode: an extracted candidate that is never embedded costs nothing.
    Only embedded assets must carry a complete visual-QA decision, and only
    embedded experimental figures need an analysis card.
    """
    errors: list[str] = []
    warnings: list[str] = []
    assets = [asset for asset in manifest.get("assets", []) if asset.get("type") in {"figure", "chart", "table"}]
    embedded = {normalize_rel(path) for path in md_image_set}

    for asset in assets:
        if asset.get("selected_strategy") == "figure_below_fallback" and normalize_rel(asset.get("path", "")) in embedded:
            errors.append(
                f"figure crop starts below its caption and cannot be embedded: {asset.get('path')}"
            )

    if not manifest_version_at_least(manifest, (2, 1)):
        return errors, warnings

    visual_qa = data.get("visual_qa", {})
    decisions = {
        normalize_rel(item.get("path", "")): item
        for item in visual_qa.get("asset_decisions", [])
        if item.get("path")
    }
    results = data.get("results_discussion", {})
    experiment_cards = {
        normalize_rel(item.get("screenshot", "")): item
        for item in results.get("experiment_figures", [])
        if item.get("screenshot")
    }
    # Reserved for a future "excluded figures must not be embedded" check; the
    # schema field exists and manifests already record it, so keep parsing it.
    _exclusions = {
        normalize_rel(item.get("path", "")): item
        for item in results.get("experiment_figure_exclusions", [])
        if item.get("path")
    }

    for asset in assets:
        path = normalize_rel(asset.get("path", ""))
        if not path:
            continue
        decision = decisions.get(path)
        embedded_asset = path in embedded

        # v3.0: only assets that actually appear in the report need a QA decision.
        if embedded_asset and not decision:
            errors.append(f"embedded visual asset has no QA decision: {path}")
            continue
        if not decision:
            continue

        status = decision.get("status")
        classification = decision.get("classification")
        if status not in {"verified", "recrop", "excluded"}:
            errors.append(f"invalid visual QA status for {path}: {status}")
        if classification not in {"experiment", "non_experiment", "table"}:
            errors.append(f"figure classification missing or invalid for {path}: {classification}")
        if embedded_asset and status != "verified":
            errors.append(f"embedded visual asset is not visually verified: {path}")
        if status == "verified" and not decision.get("caption_match"):
            errors.append(f"verified visual asset lacks caption_match confirmation: {path}")
        if embedded_asset and not decision.get("body_complete"):
            errors.append(f"embedded visual asset lacks body_complete confirmation: {path}")
        if embedded_asset and not decision.get("content_clean"):
            errors.append(f"embedded visual asset contains adjacent assets or excessive prose: {path}")
        if manifest_version_at_least(manifest, (2, 2)) and embedded_asset and not asset.get("caption_included"):
            errors.append(f"embedded visual asset crop omits its full caption: {path}")
        if asset.get("type") == "table" and classification != "table":
            errors.append(f"table must use table classification: {path}")

        if embedded_asset and asset.get("experiment_candidate") and classification != "experiment":
            errors.append(f"embedded experiment candidate cannot be classified non_experiment: {path}")

        # v3.0: cards are only required for experimental figures that are embedded.
        if embedded_asset and classification == "experiment":
            card = experiment_cards.get(path)
            if not card:
                errors.append(f"embedded experimental figure has no analysis card: {path}")

    for path, card in experiment_cards.items():
        if path not in {normalize_rel(asset.get("path", "")) for asset in assets}:
            errors.append(f"experiment figure card does not reference a manifest asset: {path}")
        elif not card.get("result") or not card.get("interpretation"):
            errors.append(f"experiment figure card lacks result or interpretation: {path}")
        elif path not in embedded:
            warnings.append(f"experiment figure card is not embedded in Markdown: {path}")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("note_dir", type=Path)
    parser.add_argument("--schema", type=Path)
    args = parser.parse_args()

    note_dir = args.note_dir
    note_json = note_dir / "note.json"
    errors: list[str] = []
    warnings: list[str] = []

    if not note_json.exists():
        errors.append(f"missing note.json: {note_json}")
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 1

    data = load_json(note_json)
    note_md, md_warnings = find_markdown(note_dir, data)
    warnings.extend(md_warnings)
    expected_timestamp = data.get("parse_started_at") or timestamp_from_folder(note_dir.name)
    if expected_timestamp and "-" in expected_timestamp:
        expected_timestamp = expected_timestamp.replace("-", "")[:12]
    expected_md_name = f"{expected_timestamp}.md" if expected_timestamp else f"{note_dir.name}.md"
    if note_md is None:
        errors.append(f"missing markdown note: expected {expected_md_name}, same-name legacy md, or note.md")
    if data.get("id") and data.get("id") != note_dir.name:
        errors.append(f"id must match folder name: {data.get('id')} != {note_dir.name}")
    md_file_field = data.get("markdown_file")
    if md_file_field and md_file_field != expected_md_name:
        errors.append(f"markdown_file must equal {expected_md_name}: {md_file_field}")
    if data.get("reading_purpose") != "standard":
        errors.append(f"reading_purpose must be standard for v1.4 notes: {data.get('reading_purpose')}")
    if errors:
        print(json.dumps({"ok": False, "markdown": str(note_md) if note_md else None, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 1
    if args.schema:
        if jsonschema is None:
            warnings.append("jsonschema is not installed; skipped schema validation")
        else:
            try:
                schema = load_json(args.schema)
                jsonschema.validate(data, schema)
            except Exception as exc:
                errors.append(f"schema validation failed: {exc}")

    md_text = note_md.read_text(encoding="utf-8")
    md_images = OBSIDIAN_IMAGE_RE.findall(md_text)
    md_images.extend(MD_IMAGE_RE.findall(md_text))
    md_image_set = {normalize_rel(rel) for rel in md_images}
    for rel in md_images:
        errors.extend(check_image(note_dir / rel))

    for figure in data.get("results_discussion", {}).get("key_figures", []):
        screenshot = figure.get("screenshot")
        if not screenshot:
            errors.append(f"key figure has no screenshot: {figure.get('ref')}")
        else:
            errors.extend(check_image(note_dir / screenshot))
            if normalize_rel(screenshot) not in md_image_set:
                warnings.append(f"key figure screenshot is not embedded near analysis in Markdown: {screenshot}")

    for formula in data.get("results_discussion", {}).get("key_formulas", []):
        screenshot = formula.get("screenshot")
        if not screenshot:
            errors.append(f"key formula has no screenshot: {formula.get('ref')}")
        else:
            errors.extend(check_image(note_dir / screenshot))
            if normalize_rel(screenshot) not in md_image_set:
                warnings.append(f"key formula screenshot is not embedded in Markdown: {screenshot}")

    visual_qa = data.get("visual_qa", {})
    if visual_qa.get("status") == "pass" and not visual_qa.get("contact_sheets"):
        warnings.append("visual_qa.status is pass but visual_qa.contact_sheets is empty")

    manifest = note_dir / "asset_manifest.json"
    if manifest.exists():
        manifest_data = load_json(manifest)
        qa_sheets = manifest_data.get("qa_contact_sheets", [])
        for rel in qa_sheets:
            errors.extend(check_image(note_dir / rel))
        if manifest_data.get("review_required") and not qa_sheets:
            warnings.append("review_required is true but no QA contact sheet was generated")
        for asset in manifest_data.get("assets", []):
            if asset.get("confidence") == "low" and asset.get("path") in md_images:
                asset_path = asset.get("path", "")
                if asset.get("type") == "formula" or "formula_candidate" in asset_path:
                    errors.append(f"low-confidence formula asset is embedded; replace with verified screenshot or remove: {asset_path}")
                else:
                    warnings.append(f"low-confidence asset is embedded; check QA contact sheet: {asset_path}")
        coverage_errors, coverage_warnings = validate_figure_coverage(data, manifest_data, md_image_set)
        errors.extend(coverage_errors)
        warnings.extend(coverage_warnings)

    ok = not errors
    print(json.dumps({"ok": ok, "markdown": str(note_md), "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
