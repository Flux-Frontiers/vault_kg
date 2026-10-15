# Release Notes -- v0.5.0

> Released: 2026-10-14

VaultKG can now bring source documents into a vault. `vaultkg add` converts a
PDF, an office document, a LaTeX or HTML file, or a Markdown or text file into
a note under the vault's sources folder, with a record of exactly where it
came from, ready for a person or an agent to write wiki pages from.

## What changed

**`vaultkg add`.** Give it files or folders and a `--kind` (for example
`articles` or `documents`). Each file becomes `RAW/<kind>/<slug>.md`, with
frontmatter that records the source's path, its SHA-256, the converter and
version that produced the text, when it was added, its title and its word
count. The original is copied beside it under `files/`. Conversion uses the
fleet's shared converters: `pymupdf4llm` for PDF, `anydoc` for office
formats, and `pandoc`, when installed, for LaTeX and HTML.

**Collisions are decided by content.** Adding the same file again does
nothing. Adding a different file under a name that is already taken writes
nothing and exits with an error; `--prefix` keeps the two apart. Notes made
before this release, which carry no recorded hash, are matched through their
copied original. A scanned PDF or a file pandoc cannot read is reported as
failed, never written as an empty note.

**The graph is untouched.** `add` only places sources; run `vaultkg build`
afterwards. No model is involved, so the same files always produce the same
notes.

**A configurable sources folder.** `raw_dir` in `.vaultkg/config.yaml` sets
where `add` writes (default `RAW`).

## Upgrading

```bash
uv tool install --force --refresh "vault-kg[semantic,viz,viz3d,ingest]==0.5.0"
```

`vaultkg add` needs the new `ingest` extra. Nothing else changes.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
