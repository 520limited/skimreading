# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Open-source project scaffolding: CI workflow, issue forms, PR template, Dependabot,
  `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `.editorconfig`, `ruff.toml`.
- README: badges, table of contents, compatibility matrix, repository layout, citation block,
  and a full Chinese version alongside the English one.

### Fixed

- `scripts/crop_display_equations.py` was GB18030-encoded; converted to UTF-8 so tooling and
  non-Chinese locales can read it.
- Lint findings across `scripts/` (unused imports/variables, import order, deprecated imports).
  No behaviour change.

## [3.2.0] - 2026-10-30

### Added

- PDF export of a finished note (`scripts/export_note_pdf.py`).
- Batch cropping of display equations (`scripts/crop_display_equations.py`).

## [3.0.0] - 2026-10-29

### Changed

- Fast mode is the default: no full-page PNG rendering, QA scoped to embedded assets only,
  merged figure cards, staged time budget.
- `validate_note.py` scoped to the fast-mode contract.

### Fixed

- `build_qa_contact_sheet.py` dropped `caption_included`, `experiment_candidate`, and
  `requires_visual_verification` when rebuilding the manifest.

### Added

- `run_lit_skim.py` orchestration (`check` / `prep` / `finalize` / `status`).

## [2.7.0] - 2026-10-25

### Changed

- Formula form and visual-asset completeness became blocking checks; formula cards are standalone.

## [2.6.0]

### Changed

- Embedded figures must include the complete caption.

## [2.5.0]

### Changed

- Experimental figure coverage added; contact sheets never count as a QA pass.

## [2.0.0]

### Added

- Dual-chain QA model, dependency checks, shareable skill folder, glossary accumulation.

## [1.0.0]

### Added

- Initial workflow: timestamped note folders, extraction, validation scripts.

[Unreleased]: https://github.com/520limited/skimreading/compare/v3.2.0...HEAD
[3.2.0]: https://github.com/520limited/skimreading/compare/v3.0.0...v3.2.0
[3.0.0]: https://github.com/520limited/skimreading/compare/v2.7.0...v3.0.0
[2.7.0]: https://github.com/520limited/skimreading/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/520limited/skimreading/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/520limited/skimreading/compare/v2.0.0...v2.5.0
[2.0.0]: https://github.com/520limited/skimreading/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/520limited/skimreading/releases/tag/v1.0.0
