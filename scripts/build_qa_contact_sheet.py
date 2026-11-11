#!/usr/bin/env python
"""Build QA contact sheets from an existing skimreading asset manifest."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from extract_pdf_assets import Asset, annotate_asset_quality, build_qa_contact_sheets


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def asset_from_manifest(item: dict) -> Asset:
    return Asset(
        path=item.get("path", ""),
        type=item.get("type", "figure"),
        ref=item.get("ref") or item.get("description") or Path(item.get("path", "asset")).stem,
        page=int(item.get("page") or 0),
        caption=item.get("caption") or item.get("description") or "",
        rect=item.get("rect") or [],
        confidence=item.get("confidence") or "low",
        notes=item.get("notes") or "",
        extraction_confidence=item.get("extraction_confidence") or item.get("confidence") or "low",
        crop_quality_score=float(item.get("crop_quality_score") or 0.0),
        crop_quality_status=item.get("crop_quality_status") or "unknown",
        qa_flags=item.get("qa_flags") or [],
        selected_strategy=item.get("selected_strategy") or "",
        candidate_count=int(item.get("candidate_count") or 1),
        # Preserve extraction-time flags; dropping them silently flips
        # caption_included/experiment_candidate to False and makes the
        # validator reject previously valid embedded crops.
        experiment_candidate=bool(item.get("experiment_candidate", False)),
        requires_visual_verification=bool(item.get("requires_visual_verification", False)),
        caption_included=bool(item.get("caption_included", False)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("note_dir", type=Path)
    args = parser.parse_args()

    note_dir = args.note_dir
    manifest_path = note_dir / "asset_manifest.json"
    figures_dir = note_dir / "figures"
    if not manifest_path.exists():
        raise SystemExit(f"missing asset_manifest.json: {manifest_path}")
    if not figures_dir.exists():
        raise SystemExit(f"missing figures directory: {figures_dir}")

    manifest = load_json(manifest_path)
    assets = [
        asset_from_manifest(item)
        for item in manifest.get("assets", [])
        if item.get("path") and (note_dir / item.get("path")).exists()
    ]

    for old_sheet in figures_dir.glob("_qa_contact_sheet*.png"):
        old_sheet.unlink()

    annotate_asset_quality(note_dir, assets)
    qa_contact_sheets = build_qa_contact_sheets(figures_dir, assets)
    low_confidence_assets = [asset for asset in assets if asset.confidence == "low"]
    manifest["asset_extraction_version"] = manifest.get("asset_extraction_version") or "2.0"
    manifest["assets"] = [asdict(asset) for asset in assets]
    manifest["qa_contact_sheets"] = qa_contact_sheets
    manifest["qa_summary"] = {
        "low_confidence_count": len(low_confidence_assets),
        "medium_or_better_count": len(assets) - len(low_confidence_assets),
        "contact_sheet_count": len(qa_contact_sheets),
    }
    manifest["review_required"] = bool(low_confidence_assets)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "asset_count": len(assets),
                "qa_contact_sheets": qa_contact_sheets,
                "manifest": str(manifest_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
