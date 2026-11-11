# Security Policy

## Supported versions

Only the latest release on `main` is supported. Fixes are shipped as a new patch release rather
than backported to older tags.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting:

- <https://github.com/520limited/skimreading/security/advisories/new>

Include the affected script, a minimal reproduction, and the impact you expect. You will get an
initial response within about a week; this is a volunteer project, so please allow time.

## Scope

skimreading parses **untrusted input** (PDFs from the internet) and writes files to a note
directory chosen by the caller. Relevant classes of issue:

- a crafted PDF causing an unexpected write outside `<notes-root>` / `<note_dir>`;
- path traversal through a paper title, filename, or manifest field;
- runaway resource use (memory / disk) on a hostile page tree;
- generated Markdown that executes content when rendered (the report is meant to be inert).

Not in scope: vulnerabilities in PyMuPDF, Pillow, jsonschema, or the agent runtime itself — report
those upstream. Also out of scope: the accuracy of a note on a malformed PDF. That is a bug, not a
security issue; open a normal issue instead.

## Handling of your data

The skill never uploads anything. All extraction happens locally, notes stay in the directory you
pass in, and no telemetry is collected or sent.
