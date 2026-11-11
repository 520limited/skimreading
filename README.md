# skimreading

[![CI](https://github.com/520limited/skimreading/actions/workflows/ci.yml/badge.svg)](https://github.com/520limited/skimreading/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Latest release](https://img.shields.io/github/v/release/520limited/skimreading?display_name=tag)](https://github.com/520limited/skimreading/releases)

**English** · [中文](#中文说明)

A DeepSeek Harness / Claude Code **skill** for fast literature skimming: turn a paper PDF into one
structured Chinese briefing note — Markdown report + `note.json` + verified figure crops.

**Target: 10–15 minutes per paper** (up to ~25 pages).

```text
PDF ──▶ scripts/prep ──▶ text + figure candidates ──▶ agent writes the note ──▶ scripts/finalize
                                                                    │
                                                    {note}.md · note.json · figures/
```

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
优点与不足与可信度 / 可借鉴之处（1-2-5）/ 个人备注 / 附录A 翻译与术语 QA / 附录B 视觉 QA.

Every claim carries a page marker like `[p.6]`.

## Why it is fast

The expensive part of a literature note is not PDF parsing — it is the model re-reading rendered
page images and hand-labelling every junk crop. This skill removes both:

| Change | Effect |
|---|---|
| No full-page PNG rendering by default | output drops from ~22 MB to ~7.5 MB per paper |
| QA decisions only for **embedded** figures | 2–4 figures checked instead of ~30 candidates |
| One card per figure | each figure analysed once, not twice |
| Staged time budget in the instructions | keeps the run bounded |

Measured on the author's machine: `prep` 7 s, extraction 8–14 s, `finalize` 3.5 s.

## Requirements

- Python ≥ 3.10
- PyMuPDF, Pillow, jsonschema (`requirements.txt`)
- Optional: Poppler (`pdftoppm` / `pdftotext` / `pdfinfo`) — the primary pipeline uses PyMuPDF

## Install

```bash
git clone https://github.com/520limited/skimreading.git
pip install -r requirements.txt
```

Copy the folder into your agent's skills directory, then restart the agent:

| Agent | Destination |
|---|---|
| Claude Code | `~/.claude/skills/skimreading/` |
| DeepSeek Harness (DSH) | `~/.agents/skills/skimreading/` or `$DSH_HOME/skills/skimreading/` |
| Codex / Cursor / other `SKILL.md` agents | that agent's skills root |

```bash
python scripts/check_environment.py                 # non-zero exit when something is missing
python scripts/check_environment.py --report-only   # JSON only, always exit 0
```

## Usage

Ask the agent to skim a paper — it loads this skill and runs:

```bash
python scripts/run_lit_skim.py prep "<paper.pdf>" "<notes-root>" --name "<title or pdf stem>"
# ... agent writes the Markdown report and note.json ...
python scripts/run_lit_skim.py finalize "<note_dir>" --notes-root "<notes-root>" --skill-version 3.0
```

`<notes-root>` must be a path you own, e.g. `~/literature-reading-notes/skimreading_notes`.
Never write notes inside the skill folder.

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

Add `--keep-pages` to `extract_pdf_assets.py` only when you need full-page images — it renders
every page to PNG and slows the run considerably.

## Scripts

| Script | Purpose |
|---|---|
| `run_lit_skim.py` | orchestration: `check` / `prep` / `finalize` / `status` |
| `make_note_dir.py` | create the timestamped output folder |
| `extract_pdf_assets.py` | page text, page map, crop candidates, QA contact sheets |
| `build_qa_contact_sheet.py` | rebuild contact sheets from an existing manifest |
| `crop_display_equations.py` | batch-crop every numbered display equation |
| `validate_note.py` | schema + figure-coverage validation |
| `check_text_quality.py` | mojibake / encoding / raw-formula detection |
| `check_formula_quality.py` | screenshot-first formula QA |
| `markdown_formula.py` | strict Markdown formula contract |
| `formula_self_test.py` | regression tests for the formula contract |
| `export_note_pdf.py` | render a finished note to PDF |
| `update_index.py` | maintain `index.json` |
| `update_glossary.py` | accumulate terminology into `glossary.json` |
| `check_environment.py` | dependency check (read-only) |

## Quality rules

- An embedded figure must include its **complete body and complete caption**, with no neighbouring
  figure, heading, or prose block.
- Only `verified` assets may be embedded; a contact sheet is *not* evidence of inspection.
- Formulas: screenshot first, intuition second, transcription last. Every equation in Markdown must
  be valid MathJax; uncertain transcription is dropped in favour of the screenshot.
- Unused extraction candidates need no QA decision — they never reach the report.

## Compatibility

| | Status |
|---|---|
| DeepSeek Harness (DSH) | ✅ primary target |
| Claude Code | ✅ `SKILL.md` + scripts |
| Codex / Cursor / other `SKILL.md` agents | ✅ if they can run shell commands |
| Windows | ⚠️ untested; scripts assume POSIX paths |

## Repository layout

```text
skimreading/
├── SKILL.md                 # the contract the agent follows
├── scripts/                 # standalone CLI entry points
├── templates/               # note-schema.json, note-template.md
├── skill_requirements.json  # machine-readable dependency manifest
├── requirements*.txt        # runtime / dev dependencies
├── ruff.toml                # lint config, shared by CI
└── .github/                 # CI, issue forms, PR template
```

## Contributing

Issues and PRs are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup, commit conventions,
and the local check suite (`ruff check .`, `python -m compileall -q scripts`,
`python scripts/formula_self_test.py`). Please follow the [Code of Conduct](CODE_OF_CONDUCT.md), and
report vulnerabilities via [SECURITY.md](SECURITY.md) rather than a public issue.

## Version

Full history in [CHANGELOG.md](CHANGELOG.md).

- **v3.2.0 (2026-10-30)** — PDF export, batch display-equation cropping.
- **v3.0.0 (2026-10-29)** — fast mode: no page rendering by default, QA scoped to embedded assets,
  merged figure cards, staged time budget, `validate_note.py` scoped accordingly.
- v2.7 — formula form and visual-asset completeness made blocking.
- v2.6 — embedded figures must include the complete caption.
- v2.5 — experimental figure coverage; contact sheets never count as a QA pass.
- v2.x — dual-chain QA model, dependency checks, glossary accumulation.
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

---

## 中文说明

> 本 README 双语：上面是英文版，这里是完整中文版，内容一一对应。

**skimreading** 是一个面向 DeepSeek Harness / Claude Code 的**技能（skill）**：把一篇论文 PDF
变成一份结构化中文文献简报——Markdown 报告 + `note.json` + 经人工核对的关键图表截图。

**目标：每篇 10–15 分钟**（25 页以内的论文）。

```text
PDF ──▶ scripts/prep ──▶ 正文文本 + 图表候选 ──▶ 由 agent 写简报 ──▶ scripts/finalize
                                                                    │
                                                    报告.md · note.json · figures/
```

### 产出什么

```text
<notes-root>/{YYYYMMDDHHMM}_{NameSlug}/
├── {YYYYMMDDHHMM}.md      # 简报正文
├── note.json              # 结构化数据，按 schema 校验
├── asset_manifest.json    # 图表来源与裁剪 QA 元数据
└── figures/               # 已核验的截图 + QA 拼图
```

报告共 9 节：文章信息 / 基本框架 / 方法与创新深解 / 关键图表、公式与实验结果 / 优点与不足与可信度 /
可借鉴之处（1-2-5）/ 个人备注 / 附录A 翻译与术语 QA / 附录B 视觉 QA。

每条结论都带页码标记，如 `[p.6]`。

### 为什么快

写文献笔记最贵的部分不是解析 PDF，而是模型反复看整页渲染图、逐张手工标记无用的裁剪图。
本技能把这两件事都去掉了：

| 做法 | 效果 |
|---|---|
| 默认不渲染整页 PNG | 单篇产出从约 22 MB 降到约 7.5 MB |
| 只对**实际嵌入**的图做 QA | 2–4 张，而不是 30 个候选 |
| 每张图只做一次卡片 | 同一张图不再分析两遍 |
| 指令里写明分段时间预算 | 运行时长可控 |

作者本机实测：`prep` 7 秒，抽取 8–14 秒，`finalize` 3.5 秒。

### 环境要求

- Python ≥ 3.10
- PyMuPDF、Pillow、jsonschema（见 `requirements.txt`）
- 可选：Poppler（`pdftoppm` / `pdftotext` / `pdfinfo`）——主流程用的是 PyMuPDF

### 安装

```bash
git clone https://github.com/520limited/skimreading.git
pip install -r requirements.txt
```

把整个文件夹复制到 agent 的技能目录，然后重启 agent：

| Agent | 技能目录 |
|---|---|
| Claude Code | `~/.claude/skills/skimreading/` |
| DeepSeek Harness (DSH) | `~/.agents/skills/skimreading/` 或 `$DSH_HOME/skills/skimreading/` |
| Codex / Cursor 等兼容 `SKILL.md` 的 agent | 各自的技能根目录 |

```bash
python scripts/check_environment.py                 # 缺依赖时返回非 0
python scripts/check_environment.py --report-only   # 只输出 JSON，始终返回 0
```

### 使用

在对话里让 agent 速读一篇论文即可，它会加载本技能并执行：

```bash
python scripts/run_lit_skim.py prep "<paper.pdf>" "<notes-root>" --name "<标题或 PDF 文件名>"
# ……agent 写 Markdown 报告与 note.json……
python scripts/run_lit_skim.py finalize "<note_dir>" --notes-root "<notes-root>" --skill-version 3.0
```

`<notes-root>` 必须是你自己拥有的路径，例如 `~/literature-reading-notes/skimreading_notes`。
不要把笔记写进技能目录。

### 手动 / 调试路径

```bash
python scripts/make_note_dir.py "<notes-root>" --name "<pdf stem>"
python scripts/extract_pdf_assets.py "<paper.pdf>" "<note_dir>" --dpi 220 --formula-candidates 1
python scripts/validate_note.py "<note_dir>" --schema templates/note-schema.json
python scripts/check_text_quality.py "<note_dir>"
python scripts/check_formula_quality.py "<note_dir>"
python scripts/update_index.py "<notes-root>" --skill-version 3.0
python scripts/update_glossary.py "<notes-root>" --note-dir "<note_dir>"
```

只有在确实需要看整页时才给 `extract_pdf_assets.py` 加 `--keep-pages`——它会把每一页渲染成
PNG，明显拖慢运行。

### 脚本一览

| 脚本 | 作用 |
|---|---|
| `run_lit_skim.py` | 编排：`check` / `prep` / `finalize` / `status` |
| `make_note_dir.py` | 创建带时间戳的输出目录 |
| `extract_pdf_assets.py` | 页文本、页映射、图表候选、QA 拼图 |
| `build_qa_contact_sheet.py` | 从已有 manifest 重建 QA 拼图 |
| `crop_display_equations.py` | 批量裁剪编号的行间公式 |
| `validate_note.py` | schema 与图表覆盖率校验 |
| `check_text_quality.py` | 乱码 / 编码 / 裸公式检测 |
| `check_formula_quality.py` | 截图优先的公式 QA |
| `markdown_formula.py` | 严格的 Markdown 公式契约 |
| `formula_self_test.py` | 公式契约回归测试 |
| `export_note_pdf.py` | 把成品简报导出为 PDF |
| `update_index.py` | 维护 `index.json` |
| `update_glossary.py` | 累积英文术语到 `glossary.json` |
| `check_environment.py` | 依赖自检（只读） |

### 质量规则

- 嵌入的图必须**完整包含图体与完整图注**，不能带邻近的图、标题或正文块。
- 只有 `verified` 的资源才能嵌入；QA 拼图**不算**已检查的证据。
- 公式：先截图、再给直觉、最后转写。写进 Markdown 的公式必须是合法 MathJax，
  拿不准的转写一律删掉、保留截图。
- 没被用到的抽取候选不需要 QA 决策——它们本来就不会进报告。

### 兼容性

| | 状态 |
|---|---|
| DeepSeek Harness (DSH) | ✅ 主要目标 |
| Claude Code | ✅ `SKILL.md` + 脚本 |
| Codex / Cursor 等 `SKILL.md` agent | ✅ 只要能执行 shell 命令 |
| Windows | ⚠️ 未测试；脚本按 POSIX 路径编写 |

### 仓库结构

```text
skimreading/
├── SKILL.md                 # agent 遵循的技能契约
├── scripts/                 # 可独立运行的 CLI 脚本
├── templates/               # note-schema.json、note-template.md
├── skill_requirements.json  # 机器可读的依赖清单
├── requirements*.txt        # 运行时 / 开发依赖
├── ruff.toml                # lint 配置，CI 共用
└── .github/                 # CI、Issue 表单、PR 模板
```

### 参与贡献

欢迎提 Issue 和 PR：开发环境、提交规范、本地检查（`ruff check .`、
`python -m compileall -q scripts`、`python scripts/formula_self_test.py`）见
[CONTRIBUTING.md](CONTRIBUTING.md)。请遵守[行为准则](CODE_OF_CONDUCT.md)；
安全问题请按 [SECURITY.md](SECURITY.md) 私下报告，不要开公开 Issue。

### 版本

完整历史见 [CHANGELOG.md](CHANGELOG.md)。

- **v3.2.0（2026-10-30）**——PDF 导出、行间公式批量裁剪。
- **v3.0.0（2026-10-29）**——快速模式：默认不渲染整页、QA 只覆盖嵌入资源、图表卡片合并、
  分段时间预算、`validate_note.py` 同步收紧。
- v2.7——公式形态与视觉资源完整性改为阻塞项。
- v2.6——嵌入图必须包含完整图注。
- v2.5——实验图覆盖率；拼图不算 QA 通过。
- v2.x——双链 QA 模型、依赖检查、可分享技能目录、术语累积。
- v1.x——初始流程、时间戳目录、校验脚本。

### 引用

```bibtex
@software{skimreading2026,
  author  = {520limited},
  title   = {skimreading: fast literature skimming skill for LLM agents},
  year    = {2026},
  url     = {https://github.com/520limited/skimreading},
  license = {MIT}
}
```

### 许可

[MIT](LICENSE) © 2026 520limited
