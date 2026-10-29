#!/usr/bin/env python
"""Small orchestration wrapper for the skimreading workflow."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_SCHEMA = SKILL_DIR / "templates" / "note-schema.json"
DEFAULT_SKILL_VERSION = "3.0"


class StepFailure(RuntimeError):
    def __init__(self, step: str, payload: dict):
        super().__init__(step)
        self.step = step
        self.payload = payload


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_json(step: str, script_name: str, args: list[str]) -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    command = [sys.executable, str(SCRIPT_DIR / script_name), *args]
    proc = subprocess.run(
        command,
        cwd=str(SKILL_DIR.parent.parent.parent.parent),
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    try:
        parsed = json.loads(stdout) if stdout else {}
    except Exception:
        try:
            parsed = json.loads(stdout.splitlines()[-1]) if stdout else {}
        except Exception:
            parsed = {"stdout": stdout}
    if proc.returncode != 0:
        raise StepFailure(
            step,
            {
                "ok": False,
                "step": step,
                "returncode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
            },
        )
    if stderr:
        parsed["stderr"] = stderr
    return parsed


def check_runtime(strict: bool = False) -> dict:
    args = ["--report-only"]
    if strict:
        args.append("--strict")
    return run_json("check_environment", "check_environment.py", args)


def require_runtime(step: str, result: dict) -> None:
    if result.get("ok"):
        return
    raise StepFailure(
        step,
        {
            "ok": False,
            "step": step,
            "message": result.get("message", "Runtime dependencies are missing."),
            "dependency_check": result,
            "next_action": "Ask the user for permission before installing the reported dependencies.",
        },
    )


def update_state(note_dir: Path, data: dict) -> dict:
    state_path = note_dir / "pipeline_state.json"
    state = load_json(state_path) if state_path.exists() else {}
    for key, value in data.items():
        if value is None:
            state.pop(key, None)
        else:
            state[key] = value
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(state_path, state)
    return state


def update_note_validation(note_dir: Path, validation: dict, visual_status: str) -> None:
    note_json = note_dir / "note.json"
    if not note_json.exists():
        return
    data = load_json(note_json)
    data["validation"] = {
        "schema_ok": bool(validation.get("ok")),
        "assets_verified": visual_status == "pass" and bool(validation.get("ok")),
        "validated_at": datetime.now().isoformat(timespec="seconds"),
        "validator": "validate_note.py; check_text_quality.py",
    }
    write_json(note_json, data)


def visual_status_from_note(note_dir: Path, qa_result: dict) -> str:
    """A contact sheet enables review; it is not evidence that review occurred."""
    if not qa_result.get("qa_contact_sheets"):
        return "unavailable"
    note_json = note_dir / "note.json"
    if not note_json.exists():
        return "warn"
    declared = load_json(note_json).get("visual_qa", {}).get("status")
    return declared if declared in {"pass", "warn", "recrop"} else "warn"


def command_prep(args: argparse.Namespace) -> int:
    runtime = check_runtime()
    require_runtime("check_environment", runtime)
    pdf = args.pdf.resolve()
    notes_root = args.notes_root.resolve()
    name = args.name or pdf.stem

    make_args = [str(notes_root), "--name", name]
    if args.timestamp:
        make_args.extend(["--timestamp", args.timestamp])
    make_result = run_json("make_note_dir", "make_note_dir.py", make_args)
    note_dir = Path(make_result["note_dir"])

    extract_args = [str(pdf), str(note_dir), "--dpi", str(args.dpi), "--formula-candidates", str(args.formula_candidates)]
    if args.keep_pages:
        extract_args.append("--keep-pages")
    extract_result = run_json("extract_pdf_assets", "extract_pdf_assets.py", extract_args)

    state = update_state(
        note_dir,
        {
            "phase": "prepared",
            "pdf": str(pdf),
            "markdown": make_result.get("markdown"),
            "text_chain_status": "prepared",
            "visual_chain_status": "pending",
            "failed_step": None,
            "error": None,
            "next_step": "Generate Markdown and note.json, then run finalize.",
        },
    )
    print(
        json.dumps(
            {
                "ok": True,
                "note_dir": str(note_dir),
                "markdown": make_result.get("markdown"),
                "extract": extract_result,
                "state": str(note_dir / "pipeline_state.json"),
                "phase": state["phase"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_finalize(args: argparse.Namespace) -> int:
    note_dir = args.note_dir.resolve()
    notes_root = args.notes_root.resolve() if args.notes_root else note_dir.parent
    schema = args.schema.resolve() if args.schema else DEFAULT_SCHEMA
    try:
        runtime = check_runtime()
        require_runtime("check_environment", runtime)
        qa_result = {}
        if (note_dir / "asset_manifest.json").exists():
            qa_result = run_json("build_qa_contact_sheet", "build_qa_contact_sheet.py", [str(note_dir)])
        formula_quality = run_json("check_formula_quality", "check_formula_quality.py", [str(note_dir)])
        validation = run_json("validate_note", "validate_note.py", [str(note_dir), "--schema", str(schema)])
        text_quality = run_json("check_text_quality", "check_text_quality.py", [str(note_dir)])
        index = {}
        if not args.skip_index:
            index = run_json("update_index", "update_index.py", [str(notes_root), "--skill-version", args.skill_version])
        glossary = run_json("update_glossary", "update_glossary.py", [str(notes_root), "--note-dir", str(note_dir)])
    except StepFailure as exc:
        state_updated = False
        if note_dir.exists():
            try:
                update_state(note_dir, {"phase": "failed", "failed_step": exc.step, "error": exc.payload})
                state_updated = True
            except Exception as state_exc:
                exc.payload["state_error"] = str(state_exc)
        exc.payload["state_updated"] = state_updated
        print(json.dumps(exc.payload, ensure_ascii=False, indent=2))
        return 1

    visual_status = visual_status_from_note(note_dir, qa_result)
    update_note_validation(note_dir, validation, visual_status)
    state = update_state(
        note_dir,
        {
            "phase": "finalized",
            "text_chain_status": "validated",
            "visual_chain_status": visual_status,
            "formula_quality": formula_quality,
            "validation": validation,
            "text_quality": text_quality,
            "index": index,
            "glossary": glossary,
            "failed_step": None,
            "error": None,
            "next_step": None,
        },
    )
    print(
        json.dumps(
            {
                "ok": True,
                "note_dir": str(note_dir),
                "visual_chain_status": visual_status,
                "formula_quality": formula_quality,
                "validation": validation,
                "text_quality": text_quality,
                "index": index,
                "glossary": glossary,
                "state": str(note_dir / "pipeline_state.json"),
                "phase": state["phase"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_status(args: argparse.Namespace) -> int:
    note_dir = args.note_dir.resolve()
    state_path = note_dir / "pipeline_state.json"
    manifest_path = note_dir / "asset_manifest.json"
    note_json = note_dir / "note.json"
    data = {
        "note_dir": str(note_dir),
        "has_markdown": bool(list(note_dir.glob("*.md"))),
        "has_note_json": note_json.exists(),
        "has_asset_manifest": manifest_path.exists(),
        "has_pipeline_state": state_path.exists(),
    }
    if state_path.exists():
        data["state"] = load_json(state_path)
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        data["asset_count"] = manifest.get("asset_count")
        data["qa_contact_sheets"] = manifest.get("qa_contact_sheets", [])
        data["review_required"] = manifest.get("review_required")
    try:
        data["dependency_check"] = check_runtime()
    except StepFailure as exc:
        data["dependency_check"] = exc.payload
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def command_check(args: argparse.Namespace) -> int:
    result = check_runtime(strict=args.strict)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prep", help="Create note directory and extract PDF assets")
    prep.add_argument("pdf", type=Path)
    prep.add_argument("notes_root", type=Path)
    prep.add_argument("--name")
    prep.add_argument("--timestamp")
    prep.add_argument("--dpi", type=int, default=220)
    prep.add_argument("--formula-candidates", type=int, default=1)
    prep.add_argument("--keep-pages", action=argparse.BooleanOptionalAction, default=False)
    prep.set_defaults(func=command_prep)

    finalize = sub.add_parser("finalize", help="Refresh QA, validate note, and update index")
    finalize.add_argument("note_dir", type=Path)
    finalize.add_argument("--notes-root", type=Path)
    finalize.add_argument("--schema", type=Path)
    finalize.add_argument("--skill-version", default=DEFAULT_SKILL_VERSION)
    finalize.add_argument("--skip-index", action="store_true")
    finalize.set_defaults(func=command_finalize)

    status = sub.add_parser("status", help="Inspect note pipeline state")
    status.add_argument("note_dir", type=Path)
    status.set_defaults(func=command_status)

    check = sub.add_parser("check", help="Check Python packages and optional Poppler tools")
    check.add_argument("--strict", action="store_true", help="Treat recommended Poppler tools as blocking")
    check.set_defaults(func=command_check)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
