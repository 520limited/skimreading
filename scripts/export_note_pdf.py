#!/usr/bin/env python
"""Export a skimreading note (Markdown) to a print-ready A4 PDF.

Three non-obvious problems this script exists to solve, all learned the hard way:

1. Python-Markdown eats LaTeX. ``$\tilde{A}_{ij}$`` contains ``_{ij}``, which
   Markdown treats as an italic marker, so the equation gets shredded into
   stray ``_`` fragments before MathJax ever sees it. Fix: stash every
   ``$$...$$`` and ``$...$`` span behind a placeholder BEFORE converting to
   HTML, then restore the original text afterwards.

2. A CDN-hosted MathJax does not render in time. With ``async`` loading plus
   ``--virtual-time-budget``, Chrome prints before the typeset pass finishes and
   the PDF ends up full of raw ``$$ ... \\frac ... $$``. Fix: ship a local
   ``tex-svg.js``, load it synchronously, and wait for ``pageReady`` to flip
   ``window.__MJ_DONE``.

3. Equations in Markdown tables are forbidden by the note schema anyway, so no
   special handling is needed there — but relative ``figures/...`` image paths
   must survive, which is why the HTML is written next to the note and printed
   with ``--allow-file-access-from-files``.

Usage:
    python export_note_pdf.py <note_dir> [--pdf <output.pdf>] [--keep-html]

Requires: Python-Markdown, a Chrome/Edge binary, and (for a clean result) one
local copy of MathJax tex-svg.js. If MathJax cannot be found or downloaded, the
script still produces a PDF but warns that equations will render as raw LaTeX.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

MATHJAX_URL = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm 14mm; }
body { font-family: "Microsoft YaHei", "Segoe UI", sans-serif; font-size: 10.5pt;
       color: #1a1a1a; line-height: 1.6; }
h1 { font-size: 17pt; color: #1a3a6b; border-bottom: 2px solid #1a3a6b;
     padding-bottom: 5px; margin-bottom: 10px; }
h2 { font-size: 13.5pt; color: #1a3a6b; margin-top: 18px;
     border-bottom: 1px solid #c8d6ea; padding-bottom: 3px; }
h3 { font-size: 11.5pt; color: #2c5a8f; margin-top: 14px; }
h4 { font-size: 10.5pt; color: #2c5a8f; margin-top: 12px; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 8px 0; }
th, td { border: 1px solid #9aa7b8; padding: 4px 6px; vertical-align: top; }
th { background: #eef3fa; }
code { font-family: Consolas, monospace; background: #f2f4f7; padding: 0 3px;
       border-radius: 3px; font-size: 9pt; }
pre { background: #f6f8fa; padding: 8px; font-size: 9pt; }
img { max-width: 100%; max-height: 118mm; display: block; margin: 8px auto; }
blockquote { border-left: 3px solid #b0c4de; margin-left: 0; padding-left: 12px;
             color: #3d3d3d; background: #fafbfd; }
hr { border: none; border-top: 1px solid #d0d0d0; margin: 14px 0; }
ul, ol { padding-left: 22px; }
"""


def find_chrome() -> str | None:
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    for name in ("chrome", "chrome.exe", "msedge", "msedge.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def ensure_mathjax(cache_dir: Path) -> Path | None:
    """Return a local tex-svg.js path, downloading it once if needed."""
    cached = cache_dir / "tex-svg.js"
    if cached.exists() and cached.stat().st_size > 100_000:
        return cached
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(MATHJAX_URL, timeout=60) as response:
            cached.write_bytes(response.read())
        if cached.stat().st_size > 100_000:
            return cached
    except Exception:
        return None
    return None


def protect_math_and_code(text: str) -> tuple[str, dict[str, str]]:
    """Stash math/code spans so Markdown cannot mangle them."""
    stash: dict[str, str] = {}

    def keep(match: re.Match[str]) -> str:
        key = f"@@SLOT{len(stash)}@@"
        stash[key] = match.group(0)
        return key

    # Order matters: code fences first (their content is literal), then display
    # math (may span lines), then inline math (single line by definition).
    text = re.sub(r"```.*?```", keep, text, flags=re.DOTALL)
    text = re.sub(r"\$\$.*?\$\$", keep, text, flags=re.DOTALL)
    text = re.sub(r"\$[^$\n]+?\$", keep, text)
    return text, stash


def build_html(markdown_text: str, mathjax_path: Path | None) -> str:
    import markdown

    protected, stash = protect_math_and_code(markdown_text)
    body = markdown.markdown(
        protected,
        extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
    )
    for key, original in stash.items():
        body = body.replace(key, original)

    if mathjax_path is not None:
        src = mathjax_path.as_posix()
        script = f"""
<script>
window.MathJax = {{
  tex: {{ inlineMath: [['$','$']], displayMath: [['$$','$$']], processEscapes: true }},
  options: {{ skipHtmlTags: ['script','noscript','style','textarea','pre','code'] }},
  svg: {{ fontCache: 'none' }},
  startup: {{
    typeset: true,
    pageReady: () => MathJax.startup.defaultPageReady().then(
      () => {{ window.__MJ_DONE = true; document.title = 'MJ_OK'; }}
    )
  }}
}};
</script>
<script src="file:///{src}"></script>
"""
    else:
        script = ""

    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{CSS}</style>{script}</head><body>{body}</body></html>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("note_dir", type=Path)
    parser.add_argument("--pdf", type=Path, default=None)
    parser.add_argument("--keep-html", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=None)
    args = parser.parse_args()

    note_dir = args.note_dir.resolve()
    if not note_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"note dir not found: {note_dir}"}, ensure_ascii=False))
        return 1

    note_json = note_dir / "note.json"
    markdown_path = None
    if note_json.exists():
        try:
            data = json.loads(note_json.read_text(encoding="utf-8"))
            declared = data.get("markdown_file")
            if declared and (note_dir / declared).exists():
                markdown_path = note_dir / declared
        except Exception:
            pass
    if markdown_path is None:
        candidates = sorted(note_dir.glob("*.md"))
        if not candidates:
            print(json.dumps({"ok": False, "error": "no markdown note found"}, ensure_ascii=False))
            return 1
        markdown_path = candidates[0]

    chrome = find_chrome()
    if chrome is None:
        print(json.dumps({"ok": False, "error": "no Chrome/Edge binary found"}, ensure_ascii=False))
        return 1

    cache_dir = args.cache_dir or Path(tempfile.gettempdir()) / "skimreading-mathjax"
    mathjax = ensure_mathjax(cache_dir)

    markdown_text = markdown_path.read_text(encoding="utf-8")
    html = build_html(markdown_text, mathjax)

    html_path = note_dir / "_export.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_path = args.pdf or (note_dir / f"{note_dir.name.split('_')[0]}.pdf")
    pdf_path = pdf_path.resolve()
    if pdf_path.exists():
        pdf_path.unlink()

    result = subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            "--allow-file-access-from-files",
            "--virtual-time-budget=25000",
            "--run-all-compositor-stages-before-draw",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ],
        capture_output=True,
        text=True,
    )

    if not args.keep_html and html_path.exists():
        html_path.unlink()

    payload = {
        "ok": pdf_path.exists(),
        "markdown": str(markdown_path),
        "pdf": str(pdf_path),
        "pdf_bytes": pdf_path.stat().st_size if pdf_path.exists() else 0,
        "mathjax": str(mathjax) if mathjax else "unavailable (equations will render as raw LaTeX)",
        "chrome": chrome,
        "stderr_tail": (result.stderr or "")[-400:],
    }

    # Post-check: a PDF full of raw LaTeX means MathJax never ran.
    if payload["ok"]:
        try:
            import pymupdf
            doc = pymupdf.open(pdf_path)
            text = "".join(doc[i].get_text() for i in range(doc.page_count))
            payload["pages"] = doc.page_count
            payload["images"] = sum(len(doc[i].get_images(full=True)) for i in range(doc.page_count))
            remnants = sum(text.count(token) for token in ("\\frac", "\\lambda", "\\mathcal", "$$"))
            payload["latex_remnants"] = remnants
            if remnants:
                payload["ok"] = False
                payload["error"] = (
                    "PDF contains raw LaTeX; MathJax did not typeset before printing"
                )
        except Exception as exc:
            payload["post_check"] = f"skipped: {exc}"

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
