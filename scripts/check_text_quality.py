#!/usr/bin/env python
"""Check Markdown/JSON text quality for translation, encoding, and formula risks."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from markdown_formula import markdown_table_lines

OBSIDIAN_IMAGE_RE = re.compile(r"!\[\[([^\]]+)\]\]")
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
FENCED_CODE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
MATH_BLOCK_RE = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$", re.DOTALL)
FORMULA_LIKE_RE = re.compile(r"([A-Za-zαβγλΔθ]_[A-Za-z0-9αβγλΔθ]|\^[{(]|\{[A-Za-z0-9_+\-*/\\\sαβγλΔθ]+\}|\\[A-Za-z]+|[A-Za-zαβγλΔθ]\s*=|[αβγλΔθ]_[A-Za-z0-9])")
CODE_LIKE_RE = re.compile(r"\b(def|class|import|for|while|return|function|const|let|var)\b")
MOJIBAKE_ERROR_PATTERNS = ["�", "锟斤拷"]
MOJIBAKE_WARNING_PATTERNS = ["Ã", "Â", "â€", "å¼", "çš", "æ"]
FULL_WIDTH_PATH_CHARS = set("（）【】，；：")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_markdown(note_dir: Path, data: dict | None = None) -> Path | None:
    declared = note_dir / data.get("markdown_file", "") if data and data.get("markdown_file") else None
    if declared and declared.exists():
        return declared
    for candidate in sorted(note_dir.glob("*.md")):
        return candidate
    return None


def check_mojibake(label: str, text: str, errors: list[str], warnings: list[str]) -> None:
    for pattern in MOJIBAKE_ERROR_PATTERNS:
        if pattern in text:
            errors.append(f"{label} contains mojibake marker: {pattern}")
    for pattern in MOJIBAKE_WARNING_PATTERNS:
        if pattern in text:
            warnings.append(f"{label} may contain mojibake sequence: {pattern}")


def check_image_paths(md_text: str, warnings: list[str]) -> None:
    paths = OBSIDIAN_IMAGE_RE.findall(md_text) + MD_IMAGE_RE.findall(md_text)
    for path in paths:
        if any(char in FULL_WIDTH_PATH_CHARS for char in path):
            warnings.append(f"image path contains full-width punctuation: {path}")
        if re.search(r"\s", path):
            warnings.append(f"image path contains whitespace; prefer ASCII slug paths: {path}")


def check_translation_qa(data: dict, md_text: str, warnings: list[str]) -> None:
    language = data.get("metadata", {}).get("language")
    if language != "en":
        return
    translation_qa = data.get("translation_qa", {})
    glossary = translation_qa.get("glossary", []) if isinstance(translation_qa, dict) else []
    has_markdown_glossary = "术语" in md_text or "glossary" in md_text.lower()
    if not glossary and not has_markdown_glossary:
        warnings.append("English paper has no translation_qa glossary or Markdown terminology section")


def check_formula_policy(data: dict, warnings: list[str]) -> None:
    formulas = data.get("results_discussion", {}).get("key_formulas", [])
    for formula in formulas:
        if formula.get("latex") and not formula.get("transcription_confidence"):
            warnings.append(f"formula has LaTeX transcription without confidence: {formula.get('ref')}")
        if formula.get("text") and not formula.get("screenshot"):
            warnings.append(f"formula text is present without screenshot-first evidence: {formula.get('ref')}")


def check_formula_code_blocks(md_text: str, warnings: list[str]) -> None:
    for match in FENCED_CODE_RE.finditer(md_text):
        block = match.group(1).strip()
        if not block:
            continue
        if FORMULA_LIKE_RE.search(block) and not CODE_LIKE_RE.search(block):
            warnings.append("formula-like content appears in a fenced code block; prefer screenshot-first or MathJax with transcription confidence")


def check_inline_formula_text(md_text: str, warnings: list[str]) -> None:
    stripped = FENCED_CODE_RE.sub("", md_text)
    stripped = MATH_BLOCK_RE.sub("", stripped)
    # Inline code spans are identifiers, file names and field names such as
    # `caption_match` or `figures/_qa_contact_sheet_01.png`. The underscore in
    # those is not a math subscript, so mask them before scanning: otherwise
    # every backticked identifier raises a false formula warning and the reader
    # spends a round trip "fixing" prose that was already correct.
    stripped = INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), stripped)
    table_rows = markdown_table_lines(stripped)
    for line_no, line in enumerate(stripped.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("!"):
            continue
        # A table cell may legitimately quote a metric like "AUC=0.87"; only
        # complete standalone equations are a real problem there, and
        # check_formula_quality.py already blocks those.
        if line_no in table_rows and "|" in line:
            continue
        if FORMULA_LIKE_RE.search(line):
            warnings.append(f"formula-like raw text outside MathJax at markdown line {line_no}; prefer screenshot or $$...$$ with confidence")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("note_dir", type=Path)
    args = parser.parse_args()

    note_dir = args.note_dir
    note_json = note_dir / "note.json"
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
    json_text = note_json.read_text(encoding="utf-8")
    check_mojibake("markdown", md_text, errors, warnings)
    check_mojibake("note.json", json_text, errors, warnings)
    check_image_paths(md_text, warnings)
    check_translation_qa(data, md_text, warnings)
    check_formula_policy(data, warnings)
    check_formula_code_blocks(md_text, warnings)
    check_inline_formula_text(md_text, warnings)

    ok = not errors
    print(
        json.dumps(
            {
                "ok": ok,
                "markdown": str(note_md),
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
