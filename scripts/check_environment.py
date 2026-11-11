#!/usr/bin/env python
"""Check runtime dependencies for the shareable skimreading skill.

This script is intentionally read-only. It reports missing dependencies and
prints install commands; an agent or user must explicitly approve installation.
"""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import shutil
import sys
from pathlib import Path

try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as distribution_version
except ImportError:  # pragma: no cover - Python 3.10+ normally has importlib.metadata
    PackageNotFoundError = Exception
    distribution_version = None


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_MANIFEST = SKILL_DIR / "skill_requirements.json"


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for part in value.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def package_version(import_name: str, distribution: str) -> str | None:
    try:
        importlib.import_module(import_name)
    except Exception:
        return None
    if distribution_version is not None:
        try:
            return str(distribution_version(distribution))
        except PackageNotFoundError:
            pass
    return "installed"


def check(manifest: dict, strict: bool = False) -> dict:
    minimum = manifest["python"]["minimum_version"]
    python_ok = version_tuple(platform.python_version()) >= version_tuple(minimum)
    python_item = {
        "name": "Python",
        "installed": platform.python_version(),
        "minimum": minimum,
        "ok": python_ok,
        "required": bool(manifest["python"].get("required", True)),
    }

    packages = []
    for item in manifest.get("python_packages", []):
        installed = package_version(item["import"], item["distribution"])
        packages.append(
            {
                "name": item["distribution"],
                "import": item["import"],
                "installed": installed,
                "ok": installed is not None,
                "required": bool(item.get("required", True)),
                "purpose": item.get("purpose", ""),
            }
        )

    executables = []
    for item in manifest.get("executables", []):
        path = shutil.which(item["name"])
        executables.append(
            {
                "name": item["name"],
                "distribution": item.get("distribution", item["name"]),
                "path": path,
                "ok": path is not None,
                "required": bool(item.get("required", False)),
                "purpose": item.get("purpose", ""),
            }
        )

    items = [python_item, *packages, *executables]
    required_missing = [item["name"] for item in items if item["required"] and not item["ok"]]
    recommended_missing = [item["name"] for item in items if not item["required"] and not item["ok"]]
    blocking_missing = required_missing + (recommended_missing if strict else [])
    install = manifest.get("install", {})
    return {
        "ok": not blocking_missing,
        "complete": not required_missing and not recommended_missing,
        "strict": strict,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "required_missing": required_missing,
        "recommended_missing": recommended_missing,
        "items": items,
        "install_commands": {
            "python_packages": install.get("python_packages_direct", "python -m pip install pymupdf pillow jsonschema"),
            "poppler_windows": install.get("poppler_windows", "winget install oschwartz10612.Poppler"),
        },
        "message": (
            "All hard requirements are available."
            if not required_missing
            else "Hard requirements are missing; install them before running the PDF pipeline."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--strict", action="store_true", help="Treat recommended executables as blocking")
    parser.add_argument("--report-only", action="store_true", help="Always exit zero after emitting the JSON report")
    args = parser.parse_args()
    try:
        result = check(load_manifest(args.manifest.resolve()), strict=args.strict)
    except Exception as exc:
        result = {"ok": False, "complete": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if args.report_only or result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
