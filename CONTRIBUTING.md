# Contributing to skimreading

Thanks for taking the time to improve this skill. This document covers the mechanics; the
[README](README.md) covers what the project does.

**Languages:** issues and PRs are welcome in English or 中文.

---

## 1. Development setup

```bash
git clone https://github.com/520limited/skimreading.git
cd skimreading
python -m venv .venv && source .venv/bin/activate   # Python ≥ 3.10
pip install -r requirements.txt -r requirements-dev.txt
```

Popper (`pdftoppm` / `pdftotext` / `pdfinfo`) is optional — the main pipeline uses PyMuPDF.
Check your environment at any time:

```bash
python scripts/check_environment.py            # exits non-zero when something is missing
python scripts/check_environment.py --report-only   # always exit 0, JSON only
```

## 2. Before you open a PR

```bash
ruff check .                          # lint (config: ruff.toml)
python -m compileall -q scripts       # syntax check
python scripts/formula_self_test.py   # formula contract regression tests
```

All three run in CI on Python 3.10–3.12. A PR that fails CI will not be reviewed.

If your change touches extraction, validation, or export, **run the affected script on a real
PDF** and say so in the PR description. A paper from arXiv works well and keeps the example
redistributable.

## 3. Repository layout

```text
skimreading/
├── SKILL.md                 # the skill contract the agent follows (single source of truth)
├── scripts/                 # CLI entry points; each is runnable on its own
├── templates/               # note-schema.json + note-template.md
├── skill_requirements.json  # machine-readable dependency manifest
├── requirements*.txt        # runtime / dev dependencies
└── .github/                 # CI, issue forms, PR template
```

Two rules of thumb:

- **`SKILL.md` is the product.** Behaviour changes (time budget, QA rules, section order) must be
  reflected there, not only in a script.
- **`scripts/` stay standalone.** Every script must run as `python scripts/<name>.py` with no
  install step, because the skill folder is copied into an agent's skills directory.

## 4. Code style

- Formatting and linting come from `ruff.toml`; do not reformat unrelated lines.
- Keep scripts dependency-light: standard library first, `requirements.txt` second.
- User-facing errors go to stderr and exit non-zero; machine-readable output goes to stdout as JSON.
- Never write outside the paths a user passes in (`<notes-root>` / `<note_dir>`). No implicit
  `~` writes, no temp files in the repo.
- Docstrings explain *why* the script exists, not just what it does.

## 5. Commit messages

Conventional Commits, one logical change per commit:

```text
feat(extract): keep caption text when cropping below-figure
fix(validate): treat missing QA decision as blocking for embedded assets
docs(readme): document the Obsidian embed path
chore(ci): pin setup-python to 3.12
```

## 6. Branches and PRs

1. Fork, or create a branch on this repo: `feat/…`, `fix/…`, `docs/…`, `chore/…`.
2. Open a PR against `main` and fill in the template.
3. Keep the PR focused. Unrelated cleanup belongs in its own PR.
4. Squash-merge is the default; the PR title becomes the commit title.

## 7. Adding a new script

- Name it after the action (`check_…`, `update_…`, `export_…`), not after the implementation.
- Accept paths as arguments; never read a fixed output directory.
- Add it to the script table in `README.md` and to the workflow section in `SKILL.md`.
- If it introduces a dependency, update `requirements.txt` **and** `skill_requirements.json`.

## 8. Reporting bugs and requesting features

Use the issue forms. Include:

- the command you ran and the full error output;
- `python scripts/check_environment.py --report-only`;
- the paper (a link is enough — please don't attach copyrighted PDFs).

## 9. Release process (maintainers)

1. Move **Unreleased** entries in `CHANGELOG.md` into a new version heading, following SemVer.
2. Bump `skill_requirements.json` / version strings referenced by `run_lit_skim.py --skill-version`.
3. Tag and publish:

   ```bash
   git tag -a v3.3.0 -m "v3.3.0"
   git push origin v3.3.0
   gh release create v3.3.0 --generate-notes
   ```

## 10. License

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
