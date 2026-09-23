# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **A documentation site** at flux-frontiers.github.io/vault_kg (MkDocs
  Material, as in connectome_kg): getting started, what the graph holds and
  how links resolve, graph health, a reference for every command, the views,
  the MCP server, KGRAG, and an API reference from the docstrings. Examples
  show real output. `docs.yml` builds it with `--strict` on every pull
  request and deploys it to GitHub Pages from `main`. A `docs` Poetry group
  holds the toolchain. `tests/test_docs_coverage.py` fails when a command,
  an MCP tool or a module is missing from the site, or a page is missing
  from the nav.
- **`vaultkg viz`**, the link graph as one self-contained interactive HTML
  page, rendered by the fleet's shared `kg_utils.viz` renderer. Notes are
  sized by backlinks and coloured by top-level folder. A root note shows its
  neighbourhood `--hops` links out, ringed in gold; without one, the most
  connected `--max-nodes` nodes. Headings are opt-in (`--headings`). Needs
  the new `viz` extra.
- **`vaultkg quilt` and `vaultkg viz3d`**: the vault grown as a 3-D tree on
  the shared `kg_utils.viz3d` growth engine. The vault is the trunk, folders
  are limbs, notes are leaves at their folder's tip, and root notes ring the
  base. A flat vault grows from nested tags instead (`--group-by auto`).
  Leaves are coloured by top-level group, first tag, or backlink count
  (`--color-by`). `quilt` frames with the shared `frame_tree` rule, prints
  the depth budget, writes a Looking Glass quilt, and can `--cast` it;
  `viz3d` is an interactive viewer with a Cast to Looking Glass action.
  `--schematic` draws the layout with straight lines. Needs the new `viz3d`
  extra.

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
- **`vaultkg` CLI**: `build`, `analyze`, `stats`, `query`, `pack`, `links`,
  `snapshot save|list|diff`. `links --in` lists a note's backlinks. Numeric
  options are range-checked at parse time (`k` 1-100, `hop` 0-5, `--limit`
  1-500).
- **`vaultkg-mcp` server** (FastMCP, stdio or SSE): `graph_stats`,
  `query_vault`, `pack_vault`, `get_node`, `note_links` (outgoing links or
  backlinks, optionally one relation), `analyze_vault`, `snapshot_list`,
  `snapshot_show` and `snapshot_diff`. `query()`/`pack()` arguments are
  validated by the `KGModule` base; node ids, link limits and snapshot keys
  are validated before use, and a snapshot key can't name a path outside the
  snapshots directory. A `lifespan` hook closes the graph when the server
  stops.
- **Clear failures instead of wrong or silent results.** `build --no-index`
  removes an existing vector index, which would otherwise describe the
  previous graph and seed queries from notes that may be gone. `query` and
  `pack` report a missing index, or a missing `semantic` extra, as a one-line
  error naming the fix, and a full `build` without that extra stops before
  writing anything rather than failing at the index step. `vaultkg-mcp` refuses to start on an unbuilt vault
  rather than creating an empty graph and reporting zero notes.
- **Backlinks include links to a note's sections.** `links --in` and the
  `note_links` MCP tool count `[[Note#Heading]]` as a backlink to the note,
  as Obsidian and `analyze` do, and each row names the node the link lands
  on (`via`). Before, a link to a section was missing from the note's
  backlinks while `analyze` counted it.
- **`VaultKG.node()` and `VaultKG.links()`**, shared by the CLI and the MCP
  server. Both accept a node id or a note's vault path (`wiki/X`,
  `wiki/X.md`, `note:wiki/X.md`).
- **Fleet tooling**: Poetry lock, a `dev` group (pytest, pytest-cov, ruff, ty,
  pre-commit, detect-secrets), pre-commit hooks that call the venv directly,
  a 90% coverage floor, and `[tool.pycodekg]`/`[tool.dockg]` index settings.
  CI runs lint, `ty`, the suite on Python 3.12 and 3.13, and an installed-wheel
  job that loads every console script, builds a vault end to end, and imports
  every submodule. `release.yml` publishes to PyPI by trusted publishing.
