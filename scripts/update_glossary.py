#!/usr/bin/env python
"""Accumulate English-paper terminology into skimreading_notes/glossary.json."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_term(term: str) -> str:
    return " ".join(term.strip().lower().split())


def iter_note_json(notes_root: Path, note_dir: Path | None):
    if note_dir:
        candidate = note_dir / "note.json"
        if candidate.exists():
            yield candidate
        return
    yield from notes_root.glob("*/note.json")


def merge_source(existing_sources: list[dict], source: dict) -> list[dict]:
    key = (source.get("note_id"), source.get("page"))
    for existing in existing_sources:
        if (existing.get("note_id"), existing.get("page")) == key:
            return existing_sources
    existing_sources.append(source)
    return existing_sources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notes_root", type=Path)
    parser.add_argument("--note-dir", type=Path)
    args = parser.parse_args()

    notes_root = args.notes_root
    glossary_path = notes_root / "glossary.json"
    glossary = load_json(glossary_path) if glossary_path.exists() else {"schema_version": "1.0", "terms": {}}
    terms = glossary.setdefault("terms", {})
    added_or_updated = 0

    for note_json in iter_note_json(notes_root, args.note_dir):
        data = load_json(note_json)
        metadata = data.get("metadata", {})
        language = metadata.get("language")
        translation_qa = data.get("translation_qa", {})
        glossary_items = translation_qa.get("glossary", []) if isinstance(translation_qa, dict) else []
        if language != "en" and not glossary_items:
            continue
        for item in glossary_items:
            original = item.get("term_original") or item.get("term") or item.get("original")
            if not original:
                continue
            key = normalize_term(original)
            entry = terms.setdefault(
                key,
                {
                    "term_original": original,
                    "term_cn": item.get("term_cn", ""),
                    "policy": item.get("policy", "bilingual"),
                    "reasons": [],
                    "sources": [],
                    "count": 0,
                },
            )
            if item.get("term_cn") and item.get("term_cn") != entry.get("term_cn"):
                entry.setdefault("variants", [])
                variant = {"term_cn": item.get("term_cn"), "source": data.get("id", note_json.parent.name)}
                if variant not in entry["variants"]:
                    entry["variants"].append(variant)
            if item.get("reason") and item.get("reason") not in entry.setdefault("reasons", []):
                entry["reasons"].append(item.get("reason"))
            source = {
                "note_id": data.get("id", note_json.parent.name),
                "title": metadata.get("title", ""),
                "page": item.get("page"),
            }
            entry["sources"] = merge_source(entry.setdefault("sources", []), source)
            entry["count"] = len(entry["sources"])
            entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
            added_or_updated += 1

    glossary["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(glossary_path, glossary)
    print(
        json.dumps(
            {
                "ok": True,
                "glossary": str(glossary_path),
                "term_count": len(terms),
                "added_or_updated": added_or_updated,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
