# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **VaultKG**, a `KGModule` for Obsidian-style Markdown vaults. Notes,
  headings (with line spans), tags (nested tags chained), attachments and
  unresolved link targets become nodes. Wikilinks, Markdown links, embeds,
  tags and typed links become edges. Typed links are Dataview inline fields
  (`supports:: [[X]]`) or frontmatter keys holding wikilinks. Everything is
  parsed, with no model extraction, so a vault always builds the same graph.
- **Obsidian link resolution**: exact path, relative path, then file name
  (same folder first, then the shortest path), then frontmatter `aliases`.
  `#Heading` anchors target the heading, and links matched by name among
  several same-named notes are marked `ambiguous`. Markdown links resolve as
  paths only. Names are NFC-folded, so macOS's decomposed file names match
  typed links. Links in code and `%%` comments are ignored.
- **Graph-health analysis** (`vaultkg analyze`): hubs, bridges (articulation
  points), wanted pages, orphans, islands, typed-link counts with every
  `contradicts` pair, tags, ambiguous links and unparseable frontmatter.
- **Fleet contracts**: frontmatter `date`/`created` map to the temporal keys
  `occurred_start`/`recorded_at`. The build stamps `_kgrag_meta` with the
  builder version, and snapshots go through the shared `SnapshotManager`.
- **`vaultkg` CLI**: `build`, `analyze`, `stats`, `query`, `pack`,
  `snapshot save|list|diff`.
