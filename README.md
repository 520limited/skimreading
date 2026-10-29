# skimreading

A DeepSeek Harness / Claude Code **skill** for fast literature skimming: turn a paper PDF into
one structured Chinese briefing note — Markdown report + `note.json` + verified figure crops.

Target: **10–15 minutes per paper** (up to ~25 pages).

---

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

Measured on this machine: `prep` 7 s, extraction 8–14 s, `finalize` 3.5 s.
The rest is model reasoning, bounded by the rules above.

## Install

Requirements: Python ≥ 3.10 with PyMuPDF, Pillow, jsonschema.

```bash
pip install -r requirements.txt
```

Poppler (`pdftoppm`/`pdftotext`/`pdfinfo`) is optional — the primary pipeline uses PyMuPDF.

Copy this folder into your agent's skills directory, e.g.:

- Claude Code / DSH: `~/.agents/skills/skimreading/`
- then restart the agent so the skill catalog is reloaded.

Check dependencies at any time:

```bash
python scripts/check_environment.py
```

## Usage

In a conversation, just ask the agent to skim a paper — it will load this skill and run:

```bash
python scripts/run_lit_skim.py prep "<paper.pdf>" "<notes-root>" --name "<title or pdf stem>"
# ... agent writes the Markdown report and note.json ...
python scripts/run_lit_skim.py finalize "<note_dir>" --notes-root "<notes-root>" --skill-version 3.0
```

`<notes-root>` must be a path you own, e.g. `~/literature-reading-notes/skimreading_notes`.
Do not write notes inside the skill folder.

### Manual / debugging path

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
| `validate_note.py` | schema + figure-coverage validation |
| `check_text_quality.py` | mojibake / encoding / raw-formula detection |
| `check_formula_quality.py` | screenshot-first formula QA |
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

## Version

- **v3.0 (2026-10-29)** — fast mode: no page rendering by default, QA scoped to embedded assets,
  merged figure cards, staged time budget, `validate_note.py` scoped accordingly,
  and a fix for `build_qa_contact_sheet.py` dropping `caption_included` /
  `experiment_candidate` / `requires_visual_verification` when rebuilding the manifest.
- v2.7 — formula form and visual-asset completeness made blocking; standalone formula cards.
- v2.6 — embedded figures must include the complete caption.
- v2.5 — experimental figure coverage; contact sheets never count as a QA pass.
- v2.x — dual-chain QA model, dependency checks, shareable skill folder, glossary accumulation.
- v1.x — initial workflow, timestamped folders, validation scripts.

## License

MIT
