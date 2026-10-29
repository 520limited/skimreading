#!/usr/bin/env python
"""Idempotently update skimreading_notes/index.json from note.json files."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def entry_from_note(note_json: Path) -> dict:
    data = load_json(note_json, {})
    metadata = data.get("metadata", {})
    parse_started_at = data.get("parse_started_at", "")
    expected_md = f"{parse_started_at}.md" if parse_started_at else ""
    preferred_md = note_json.parent / expected_md if expected_md else note_json.parent / f"{note_json.parent.name}.md"
    same_name_md = note_json.parent / f"{note_json.parent.name}.md"
    legacy_md = note_json.parent / "note.md"
    md_file = preferred_md.name if preferred_md.exists() else same_name_md.name if same_name_md.exists() else legacy_md.name if legacy_md.exists() else ""
    return {
        "id": data.get("id") or note_json.parent.name,
        "title": metadata.get("title", ""),
        "first_author": metadata.get("first_author", ""),
        "journal": metadata.get("journal", ""),
        "year": metadata.get("year"),
        "reading_purpose": data.get("reading_purpose", ""),
        "keywords": metadata.get("keywords", []),
        "created_at": data.get("created_at", ""),
        "parse_started_at": parse_started_at,
        "markdown_file": data.get("markdown_file", md_file),
        "directory": note_json.parent.name,
        "markdown": md_file,
        "is_demo": bool(data.get("is_demo", False)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notes_root", type=Path)
    parser.add_argument("--skill-version", default="1.2")
    args = parser.parse_args()

    notes_root = args.notes_root
    index_path = notes_root / "index.json"
    index = load_json(
        index_path,
        {"version": "1.0", "description": "Literature reading notes index", "entries": []},
    )

    entries = []
    for note_json in sorted(notes_root.glob("*/note.json")):
        entries.append(entry_from_note(note_json))

    index["entries"] = entries
    index["total_count"] = len(entries)
    index["skill_version"] = args.skill_version
    index["last_updated"] = datetime.now(timezone.utc).isoformat()
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"updated": str(index_path), "total_count": len(entries)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
