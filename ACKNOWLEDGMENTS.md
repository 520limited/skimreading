# Acknowledgements / 致谢

## Upstream project / 上游项目

`skimreading` is derived from the **`skimreading` skill** in
[sleep-nobad/literature-reading-skills](https://github.com/sleep-nobad/literature-reading-skills),
licensed under MIT and © 2026 Literature Reading Skills Contributors.

本仓库的 `skimreading` 技能派生自
[sleep-nobad/literature-reading-skills](https://github.com/sleep-nobad/literature-reading-skills)
中的 `skimreading` 技能（MIT 许可，© 2026 Literature Reading Skills Contributors）。

## What came from upstream / 来自上游的部分

- the two-phase workflow — `prep` → the agent writes the note → `finalize`（两阶段流程）
- the note folder layout (`{timestamp}_{slug}/` with `note.json`, `asset_manifest.json`, `figures/`)
  笔记目录结构
- the PDF extraction pipeline (`extract_pdf_assets.py`, contact sheets, candidate scoring)
  抽取管线
- the JSON schemas (`templates/note-schema.json`) and the note template 数据结构与模板
- the QA rules enforced by `validate_note.py`, `check_text_quality.py`,
  `check_formula_quality.py`, and `markdown_formula.py`（QA 规则）
- the staged time budget that makes a 10–15 minute run feasible 分段时间预算

The upstream repository also ships an `intensivereading` skill for tutor-style deep reading.
It is **not** included here; this repository is the fast-skimming half only.

上游仓库还包含 `intensivereading`（导师式精读）技能，本仓库**未**收录，只包含速读这一半。

## What this repository adds / 本仓库新增

- `scripts/export_note_pdf.py` — render a finished note to PDF
- `scripts/crop_display_equations.py` — batch-crop display equations
- packaging for agents besides Codex (DSH / Claude Code skill layout, dependency checks)
- CI (Python 3.10–3.12), ruff config, issue/PR templates, Dependabot
- bilingual README, CHANGELOG, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY
- bug fixes: GB18030 → UTF-8 script encoding; PyMuPDF 2.x import compatibility; lint findings

## Thanks / 感谢

Thank you to the upstream authors for publishing the workflow, the schemas, and the QA rules
openly. The hard part of this project — deciding what a trustworthy literature note looks like and
enforcing it mechanically — was designed upstream; everything here builds on that.

感谢上游作者把流程、数据结构和 QA 规则公开出来。这个项目里最难的部分——"一份可信的文献笔记
应该长什么样"以及如何用脚本机械地保证它——都是上游设计的，本仓库只是在其上继续搭建。

If you use this repository, please consider starring the upstream project as well:
<https://github.com/sleep-nobad/literature-reading-skills>

## License / 许可

Both works are MIT. The [`LICENSE`](LICENSE) file in this repository carries both copyright notices,
as the MIT license requires.
