# Install and build a vault

**Requirements:** Python >= 3.12, < 3.14

## Install

To use the `vaultkg` and `vaultkg-mcp` commands from any directory, install
them as a tool:

```bash
uv tool install "vault-kg[semantic]"      # or: pipx install "vault-kg[semantic]"
```

To use VaultKG as a library in your own project:

```bash
pip install "vault-kg[semantic]"
```

Pick the extras for what you need:

| Extra | Adds | Needed by |
|---|---|---|
| (none) | Graph build, analysis, links, snapshots, the MCP server | everything not listed below |
| `semantic` | PyTorch, sentence-transformers and the sqlite-vec index | a full `build`, `query`, `pack`, and the `query_vault` / `pack_vault` MCP tools |
| `viz` | pyvis, through `kgmodule-utils[viz]` | `vaultkg viz` |
| `viz3d` | PyVista, PyQt5, pyvistaqt and quiltwright | `vaultkg quilt`, `vaultkg viz3d` |

The first full build downloads the embedding model, `BAAI/bge-small-en-v1.5`,
about 130 MB. A command that needs a missing extra stops and names the
`pip install` line.

To work on VaultKG itself, install from a clone:

```bash
git clone https://github.com/Flux-Frontiers/vault_kg.git
cd vault_kg
poetry install --with dev --all-extras
```

## Build a vault

```bash
vaultkg build --vault ~/brain --exclude templates
```

`build` parses every note, resolves every link, and embeds notes and
sections for search. On the seven-note vault used in these pages it prints:

```text
nodes       : 22  {'attachment': 1, 'heading': 8, 'note': 7, 'symbol': 2, 'tag': 4}
edges       : 25  {'CONTAINS': 9, 'CONTRADICTS': 1, 'EMBEDS': 1, 'EXTENDS': 1, 'LINKS_TO': 9, 'SUPPORTS': 1, 'TAGGED': 3}
indexed     : 15 vectors  dim=384
```

`symbol` nodes are link targets no note answers to; see
[What the graph holds](graph.md).

- `--no-index` builds the graph without embeddings. `analyze`, `stats`,
  `links`, `snapshot` and the views work without them; `query` and `pack` do
  not.
- `--exclude PATTERN` (repeatable) skips folders such as `templates` or
  `raw`, by name or by glob on the vault-relative path. Dot-folders
  (`.obsidian/`, `.trash/`, `.vaultkg/`) are always skipped.

## Search it

```bash
vaultkg query --vault ~/brain "why do long contexts fail" -k 3
```

```text
0.779  hop0  heading  heading:wiki/concepts/Retrieval.md#failure-modes
0.750  hop0  heading  heading:wiki/concepts/Retrieval.md#retrieval-augmented-generation
0.727  hop0  note     note:wiki/concepts/Retrieval.md
0.779  hop1  note     note:wiki/concepts/Search.md
0.727  hop1  note     note:wiki/sources/Lost in the Middle.md
...
```

The `hop0` rows are the semantic hits; the `hop1` rows are reached from them
by one link. `vaultkg pack` runs the same search and prints each note's or
section's text as Markdown, ready to hand to a model.

A note can be named by its node id (`note:wiki/Retrieval.md`) or by its vault
path, with or without `.md`. `--vault` defaults to the current directory.

## Keep the graph current

`build` rebuilds the whole graph from the notes on disk; there's no
incremental update. Run it again after you edit the vault.

- **Excluded folders aren't remembered.** Pass the same `--exclude` options on
  every build, or the next build indexes those folders again.
- **Keep the default `--wipe`.** `--no-wipe` adds and updates nodes but never
  removes them, so deleted and renamed notes stay in the graph.
- **`--no-index` removes an existing vector index**, because an index from an
  earlier build no longer matches the graph. Run a full `build` before you
  use `query` or `pack` again.

## Where the graph is stored

`build` writes to `<vault>/.vaultkg/`:

| Path | Contents |
|---|---|
| `graph.sqlite` | Nodes and edges |
| `vectors.sqlite` | The vector index (full builds only) |
| `snapshots/` | Metric snapshots from `vaultkg snapshot save` |

Obsidian ignores dot-folders, so the store never shows up as a note. If the
vault is a git repository, ignore the databases and keep the snapshots:

```gitignore
.vaultkg/*.sqlite
.vaultkg/*.sqlite-*
```

If a sync service copies the vault between devices, exclude `.vaultkg/` there
and rebuild on each device.
