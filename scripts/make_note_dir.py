#!/usr/bin/env python
"""Create a timestamped skimreading note directory."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


def safe_name(value: str, limit: int = 90) -> str:
    value = value.strip()
    value = re.sub(r"\.[Pp][Dd][Ff]$", "", value)
    chars = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_"}:
            chars.append(ch)
        elif ch.isspace() or ch in {".", ",", ":", ";", "—", "–", "(", ")", "[", "]", "{", "}"}:
            chars.append("_")
    out = re.sub(r"_+", "_", "".join(chars)).strip("_-")
    return (out or "paper")[:limit].strip("_-") or "paper"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notes_root", type=Path)
    parser.add_argument("--name", required=True, help="Paper title, PDF stem, or user-facing report name")
    parser.add_argument("--timestamp", help="Override timestamp, format YYYYMMDDHHMM")
    args = parser.parse_args()

    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d%H%M")
    if not re.match(r"^\d{12}$", timestamp):
        raise SystemExit("--timestamp must match YYYYMMDDHHMM")

    stem = f"{timestamp}_{safe_name(args.name)}"
    note_dir = args.notes_root / stem
    note_dir.mkdir(parents=True, exist_ok=False)
    (note_dir / "figures").mkdir()

    result = {
        "stem": stem,
        "timestamp": timestamp,
        "note_dir": str(note_dir),
        "markdown": str(note_dir / f"{timestamp}.md"),
        "json": str(note_dir / "note.json"),
        "figures_dir": str(note_dir / "figures"),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
