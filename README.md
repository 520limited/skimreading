# skimreading

[![CI](https://github.com/520limited/skimreading/actions/workflows/ci.yml/badge.svg)](https://github.com/520limited/skimreading/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Latest release](https://img.shields.io/github/v/release/520limited/skimreading?display_name=tag)](https://github.com/520limited/skimreading/releases)

A DeepSeek Harness / Claude Code **skill** for fast literature skimming: turn a paper PDF into one
structured Chinese briefing note — Markdown report + `note.json` + verified figure crops.

**Target: 10–15 minutes per paper** (up to ~25 pages).

```text
PDF ──▶ scripts/prep ──▶ text + figure candidates ──▶ agent writes the note ──▶ scripts/finalize
                                                                    │
                                                    {note}.md · note.json · figures/
```

---

## Contents

- [What it produces](#what-it-produces)
- [Why it is fast](#why-it-is-fast)
- [Requirements](#requirements)
- [Install](#install)
- [Usage](#usage)
- [Manual / debugging path](#manual--debugging-path)
- [Scripts](#scripts)
- [Quality rules](#quality-rules)
- [Compatibility](#compatibility)
- [Repository layout](#repository-layout)
- [Contributing](#contributing)
- [Version](#version)
- [Citation](#citation)
- [License](#license)

## What it produces

```text
<notes-root>/{YYYYMMDDHHMM}_{NameSlug}/
├── {YYYYMMDDHHMM}.md      # the report
├── note.json              # structured data, schema-validated
├── asset_manifest.json    # figure/table provenance + crop QA metadata
└── figures/               # verified crops + QA contact sheets
```

The report has 9 sections: 文章信息 / 基本框架 / 方法与创新深解 / 关键图表、公式与实验结果 /
优点与不足与可信度 / 可借鉴之处（1-2-5）/ 个人备注 / 附录A 翻译与术语 QA / 附录B 视觉 QA。

Every claim carries a page marker like `[p.6]`.

## Why it is fast

The expensive part of a literature note is not PDF parsing — it is the model re-reading rendered
page images and hand-labelling every junk crop. This skill removes both:

| Change | Effect |
|---|---|
| No full-page PNG rendering by default | output drops from ~22 MB to ~7.5 MB per paper; the model reads text, not 25 large images |
| QA decisions only for **embedded** figures | 2–4 figures checked instead of ~30 candidates |
| One card per figure (no separate "experiment figure" pass) | each figure analysed once, not twice |
| Staged time budget in the instructions | keeps the run bounded |

Measured on the author's machine: `prep` 7 s, extraction 8–14 s, `finalize` 3.5 s.
The rest is model reasoning, bounded by the rules above.

## Requirements

- Python ≥ 3.10
- Python packages: PyMuPDF, Pillow, jsonschema (`requirements.txt`)
- Optional: Poppler (`pdftoppm` / `pdftotext` / `pdfinfo`) — the primary pipeline uses PyMuPDF

## Install

```bash
git clone https://github.com/520limited/skimreading.git
pip install -r requirements.txt
```

Then copy the folder into your agent's skills directory and restart the agent:

| Agent | Destination |
|---|---|
| Claude Code | `~/.claude/skills/skimreading/` |
| DeepSeek Harness (DSH) | `~/.agents/skills/skimreading/` or `$DSH_HOME/skills/skimreading/` |
| Codex / Cursor / other `SKILL.md`-compatible agents | that agent's skills root |

Check dependencies at any time:

```bash
python scripts/check_environment.py             # non-zero exit when something is missing
python scripts/check_environment.py --report-only   # JSON only, always exit 0
```

## Usage

In a conversation, ask the agent to skim a paper — it loads this skill and runs:

```bash
python scripts/run_lit_skim.py prep "<paper.pdf>" "<notes-root>" --name "<title or pdf stem>"
# ... agent writes the Markdown report and note.json ...
python scripts/run_lit_skim.py finalize "<note_dir>" --notes-root "<notes-root>" --skill-version 3.0
```

`<notes-root>` must be a path you own, e.g. `~/literature-reading-notes/skimreading_notes`.
Do not write notes inside the skill folder.

## Manual / debugging path

```bash
python scripts/make_note_dir.py "<notes-root>" --name "<pdf stem>"
python scripts/extract_pdf_assets.py "<paper.pdf>" "<note_dir>" --dpi 220 --formula-candidates 1
python scripts/validate_note.py "<note_dir>" --schema templates/note-schema.json
python scripts/check_text_quality.py "<note_dir>"
python scripts/check_formula_quality.py "<note_dir>"
python scripts/update_index.py "<notes-root>" --skill-version 3.0
python scripts/update_glossary.py "<notes-root>" --note-dir "<note_dir>"
```

Add `--keep-pages` to `extract_pdf_assets.py` only when you actually need to inspect full pages —
it renders every page to PNG and slows the run considerably.

## Scripts

| Script | Purpose |
|---|---|
| `run_lit_skim.py` | orchestration: `check` / `prep` / `finalize` / `status` |
| `make_note_dir.py` | create the timestamped output folder |
| `extract_pdf_assets.py` | page text, page map, figure/table/formula crop candidates, QA contact sheets |
| `build_qa_contact_sheet.py` | rebuild contact sheets from an existing manifest |
| `crop_display_equations.py` | batch-crop every numbered display equation |
| `validate_note.py` | schema + figure-coverage validation |
| `check_text_quality.py` | mojibake / encoding / raw-formula detection |
| `check_formula_quality.py` | screenshot-first formula QA |
| `markdown_formula.py` | strict Markdown formula contract (library + CLI) |
| `formula_self_test.py` | regression tests for the formula contract |
| `export_note_pdf.py` | render a finished note to PDF |
| `update_index.py` | maintain `skimreading_notes/index.json` |
| `update_glossary.py` | accumulate English terminology into `glossary.json` |
| `check_environment.py` | dependency check (read-only) |

## Quality rules

- An embedded figure must include its **complete body and complete caption**, with no neighbouring
  figure, heading, or prose block.
- Only `verified` assets may be embedded; a generated contact sheet is *not* evidence of inspection.
- Formulas: screenshot first, intuition second, transcription last. Any equation written in Markdown
  must be valid MathJax; uncertain transcription is omitted in favour of the screenshot.
- Unused extraction candidates need no QA decision — they simply never reach the report.

## Compatibility

| | Status |
|---|---|
| DeepSeek Harness (DSH) | ✅ primary target |
| Claude Code | ✅ `SKILL.md` + scripts |
| Codex / Cursor / other `SKILL.md` agents | ✅ if they can run shell commands |
| Windows | ⚠️ untested; scripts use POSIX paths |

## Repository layout

```text
skimreading/
├── SKILL.md                 # the contract the agent follows
├── scripts/                 # standalone CLI entry points
├── templates/               # note-schema.json, note-template.md
├── skill_requirements.json  # machine-readable dependency manifest
├── requirements.txt         # runtime deps
├── requirements-dev.txt     # lint/test deps
├── ruff.toml                # lint config (shared by CI)
└── .github/                 # CI, issue forms, PR template
```

## Contributing

Issues and PRs are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup, commit conventions,
and the local check suite (`ruff check .`, `python -m compileall -q scripts`,
`python scripts/formula_self_test.py`). Please follow the [Code of Conduct](CODE_OF_CONDUCT.md) and
report vulnerabilities via [SECURITY.md](SECURITY.md) — not in a public issue.

## Version

See [CHANGELOG.md](CHANGELOG.md) for the full history.

- **v3.2.0 (2026-10-30)** — PDF export, batch display-equation cropping.
- **v3.0.0 (2026-10-29)** — fast mode: no page rendering by default, QA scoped to embedded assets,
  merged figure cards, staged time budget, `validate_note.py` scoped accordingly, and a fix for
  `build_qa_contact_sheet.py` dropping `caption_included` / `experiment_candidate` /
  `requires_visual_verification` when rebuilding the manifest.
- v2.7 — formula form and visual-asset completeness made blocking; standalone formula cards.
- v2.6 — embedded figures must include the complete caption.
- v2.5 — experimental figure coverage; contact sheets never count as a QA pass.
- v2.x — dual-chain QA model, dependency checks, shareable skill folder, glossary accumulation.
- v1.x — initial workflow, timestamped folders, validation scripts.

## Citation

```bibtex
@software{skimreading2026,
  author  = {520limited},
  title   = {skimreading: fast literature skimming skill for LLM agents},
  year    = {2026},
  url     = {https://github.com/520limited/skimreading},
  license = {MIT}
}
```

## License

[MIT](LICENSE) © 2026 520limited
