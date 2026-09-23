[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: Elastic-2.0](https://img.shields.io/badge/License-Elastic%202.0-blue.svg)](https://www.elastic.co/licensing/elastic-license)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/Flux-Frontiers/vault_kg/releases)
[![CI](https://github.com/Flux-Frontiers/vault_kg/actions/workflows/ci.yml/badge.svg)](https://github.com/Flux-Frontiers/vault_kg/actions/workflows/ci.yml)
[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)
[![Docs](https://github.com/Flux-Frontiers/vault_kg/actions/workflows/docs.yml/badge.svg)](https://flux-frontiers.github.io/vault_kg/)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.22907544-blue.svg)](https://doi.org/10.5281/zenodo.22907544)

# VaultKG -- Obsidian Vaults as Knowledge Graphs

**VaultKG turns an Obsidian-style Markdown vault into a queryable knowledge graph. Every edge is a link the author wrote.**

A vault already is a graph: pages are nodes, `[[wikilinks]]` are edges, and
people who keep typed links (`supports:: [[X]]`) have written down what kind of
edge. VaultKG reads that structure directly. It doesn't use a language model to
extract entities or guess relations, so the same vault always builds the same
graph.

Embeddings are used only to find entry points for a search. Everything after
that follows the stored links, as in the rest of the
[KGRAG](https://github.com/Flux-Frontiers/KGRAG) fleet. VaultKG is a `KGModule`
built on [kgmodule-utils](https://github.com/Flux-Frontiers/KG_utils), so a
vault federates with code, documents and every other KG kind through KGRAG.

*Author: Eric G. Suchanek, PhD -- Flux-Frontiers, Liberty TWP, OH*

**Documentation:** [flux-frontiers.github.io/vault_kg](https://flux-frontiers.github.io/vault_kg/)
covers installation, the graph, graph health, every command, the views, the
MCP server and the API.

> **Status: alpha (0.1.0).** Build, link resolution, graph-health analysis,
> query and pack, snapshots, the 2-D link graph, the 3-D tree with Looking
> Glass quilts, the `vaultkg` CLI and the `vaultkg-mcp` server work end to end,
> and have been run against a 250-note vault. The KGRAG adapter
> (kind `vault`) is merged into KGRAG and ships in its next release.

---

## Sister projects

VaultKG is part of the **KGRAG** family: knowledge-graph systems that share one
hybrid semantic-plus-structural design, each for a different kind of corpus.

- **[DocKG](https://github.com/Flux-Frontiers/doc_kg)** -- document corpora (`.md`, `.txt`, `.rst`, `.pdf`). Use DocKG for prose without links; use VaultKG when the links are the point.
- **[PyCodeKG](https://github.com/Flux-Frontiers/pycode_kg)** -- Python source code: modules, classes, functions and their typed relationships.
- **[DiaryKG](https://github.com/Flux-Frontiers/diary_kg)** -- personal journals and diary corpora.
- **[GenealogyKG](https://github.com/Flux-Frontiers/genealogy_kg)** -- GEDCOM family-history files.
- **[ConnectomeKG](https://github.com/Flux-Frontiers/connectome_kg)** -- electron-microscopy connectomes.
- **[AgentKG](https://github.com/Flux-Frontiers/agent_kg)** -- conversational memory as a knowledge graph.

---

## Get started

**Requirements:** Python >= 3.12, < 3.14

To use the `vaultkg` and `vaultkg-mcp` commands from any directory, install
them as a tool:

```bash
uv tool install "vault-kg[semantic]"      # or: pipx install "vault-kg[semantic]"
```

To use VaultKG as a library in your own project:

```bash
pip install "vault-kg[semantic]"
```

The `semantic` extra adds the embedding stack (PyTorch and
sentence-transformers) for `query`, `pack` and the matching MCP tools. The
first full build downloads the embedding model, `BAAI/bge-small-en-v1.5`, about
130 MB. Without the extra, `build --no-index`, `analyze`, `stats`, `links`,
`snapshot` and the rest of the MCP server work, and `query` says which package
is missing.

Two more extras add the views; install them together with `semantic` or on
their own:

| Extra | Adds |
|---|---|
| `viz` | `vaultkg viz`, the interactive 2-D link graph (pyvis) |
| `viz3d` | `vaultkg quilt` and `vaultkg viz3d`, the vault grown as a 3-D tree (PyVista, PyQt5, quiltwright) |

```bash
uv tool install "vault-kg[semantic,viz,viz3d]"
```

To work on VaultKG itself, install from a clone:

```bash
git clone https://github.com/Flux-Frontiers/vault_kg.git
cd vault_kg
poetry install --with dev --all-extras
```

### Build and query a vault

```bash
vaultkg build --vault ~/brain                 # writes ~/brain/.vaultkg/
vaultkg analyze --vault ~/brain               # graph-health report
vaultkg query --vault ~/brain "why long contexts fail"
vaultkg pack  --vault ~/brain "why long contexts fail"
vaultkg links --vault ~/brain --in wiki/Retrieval     # backlinks
vaultkg snapshot save --vault ~/brain
```

A note can be named by its node id (`note:wiki/Retrieval.md`) or by its vault
path, with or without `.md`. `--vault` defaults to the current directory.

### Keep the graph current

`build` rebuilds the whole graph from the notes on disk; there's no incremental
update. Run it again after you edit the vault.

- **Excluded folders aren't remembered.** Pass the same `--exclude` options on
  every build, or the next build indexes those folders again.
- **Keep the default `--wipe`.** `--no-wipe` adds and updates nodes but never
  removes them, so deleted and renamed notes stay in the graph.
- **`--no-index` removes an existing vector index**, because an index from an
  earlier build no longer matches the graph. Run a full `build` before you use
  `query` or `pack` again.

### Where the graph is stored

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

---

## CLI reference

Every command takes `--vault DIR` (default: the current directory) and `--help`.

| Command | What it does | Options |
|---|---|---|
| `vaultkg build` | Parse the vault into a graph and a vector index | `--exclude PATTERN` (repeatable; a folder name or a glob on vault-relative paths), `--no-index`, `--wipe/--no-wipe` (default `--wipe`) |
| `vaultkg analyze` | Print the graph-health report | `--json` for the metrics as JSON |
| `vaultkg stats` | Print node and edge counts as JSON | |
| `vaultkg query Q` | Semantic search, then expansion along links | `-k` seed hits (1-100, default 8), `--hop` link hops (0-5, default 1), `--json` for the full result |
| `vaultkg pack Q` | The same search, printed as Markdown with each note's text | `-k`, `--hop` |
| `vaultkg links NODE` | A node's outgoing links | `--in` for backlinks, `--rel REL` for one relation, `--limit` (1-500, default 50) |
| `vaultkg snapshot save [KEY]` | Record the current metrics (key defaults to a UTC timestamp) | `--force` to save when nothing changed |
| `vaultkg snapshot list` | List snapshots, newest first | |
| `vaultkg snapshot diff A B` | Compare two snapshots | |
| `vaultkg viz [ROOT]` | Write the link graph as an interactive HTML page | `-o FILE` (default `<vault name>_links.html`), `--hops` (0-5, default 1), `--max-nodes` (2-5000, default 200), `--headings` |
| `vaultkg quilt` | Grow the vault as a 3-D tree and render a Looking Glass quilt | `--preset` (default `16-landscape`), `-o DIR` (default `renders`), `--group-by`, `--color-by`, `--tip-radius`, `--leaf-size`, `--zoom`, `--fov`, `--cast`, `--schematic` |
| `vaultkg viz3d` | Open the 3-D tree in an interactive viewer | `--group-by`, `--color-by`, `--preset`, `--width`, `--height`, `--schematic` |
| `vaultkg --version` | Print the installed version | |

`query` and `pack` need the `semantic` extra and a build without `--no-index`.
`viz` needs the `viz` extra; `quilt` and `viz3d` need `viz3d`. The other
commands need only a built graph.

---

## What becomes the graph

| Node | From |
|---|---|
| `note` | every `.md` file |
| `heading` | every ATX heading, as a section with its line span |
| `tag` | `#tag` and frontmatter `tags:`; nested tags chain (`#ml` -> `#ml/retrieval`) |
| `attachment` | an embedded or linked non-Markdown file |
| unresolved | a link target no file answers to (Obsidian's "unresolved links") |

| Edge | From |
|---|---|
| `LINKS_TO` | `[[Page]]`, `[[Page\|alias]]`, `[text](page.md)`, `[text](folder/)` |
| `EMBEDS` | `![[Page]]`, `![[image.png]]` |
| `CONTAINS` | note -> heading -> subheading, tag -> nested tag |
| `TAGGED` | note -> tag |
| typed | Dataview inline fields (`(supports:: [[X]])`, `- up:: [[Home]]`) and frontmatter keys holding wikilinks (`contradicts: ["[[Y]]"]`). These become `SUPPORTS`, `UP`, `CONTRADICTS` and so on. |

Links resolve the way Obsidian resolves them, in this order:

1. The exact vault path.
2. A path relative to the linking note.
3. The file name, in the same folder first, then the shortest path.
4. A frontmatter `aliases` entry.

`[[Page#Heading]]` points at the heading. A Markdown link is a path and never
resolves by name. Wikilinks inside code blocks, inline code and `%% comments %%`
are ignored. A link that matched several same-named notes is marked `ambiguous`.

Frontmatter `date` becomes the fleet's `occurred_start` and `created` becomes
`recorded_at`, so KGRAG time-scoped queries can filter notes by date. File
modification times aren't used, because they change on every clone.

---

## Graph health

`vaultkg analyze` reports these figures, computed from the graph alone:

- **Hubs**: the notes that the most other notes link to.
- **Bridges**: notes whose removal would split the graph (articulation points).
- **Wanted pages**: link targets with no note, ranked by how many notes want them.
- **Orphans**: notes with no links in or out.
- **Islands**: linked groups cut off from the main graph.
- **Typed links**: counts per relation, with every `contradicts` pair listed.
- **Tags**, **ambiguous links**, and **frontmatter that failed to parse**.

`vaultkg analyze --json` prints the same figures as JSON. `vaultkg snapshot
save` records them, so `snapshot diff` shows how a vault's structure changed
between two dates.

---

## See the vault

### The link graph

`vaultkg viz` writes one self-contained HTML page that opens from disk in any
browser, with no server:

```bash
vaultkg viz --vault ~/brain                          # the most connected part of the vault
vaultkg viz --vault ~/brain wiki/Retrieval --hops 2  # one note's neighbourhood
```

- Notes are sized by backlinks, so hubs stand out, and coloured by top-level
  folder. Tags are diamonds, attachments squares, and missing notes grey
  triangles.
- With a root note, the page shows everything within `--hops` links of it,
  in either direction, and rings the root in gold. Without one, it shows the
  most connected `--max-nodes` nodes.
- Headings are left out unless you pass `--headings`; a vault has several per
  note, and they hide the links between notes.
- Drag to pan, scroll to zoom, and click a node for its details.

### The vault as a tree

`vaultkg quilt` and `vaultkg viz3d` grow the vault as a 3-D tree: the vault is
the trunk, each folder is a limb, subfolders branch off their parent, and
every note is a leaf at the tip of its folder. Notes at the vault root ring
the base of the trunk. A bigger folder grows a longer limb. The growth is
seeded from the vault's name, so the same vault always grows the same tree.

```bash
vaultkg quilt --vault ~/brain                     # writes renders/brain_qs8x6a1.77778.png
vaultkg quilt --vault ~/brain --color-by links --cast
vaultkg viz3d --vault ~/brain                     # interactive; orbit, zoom, pan
```

| Option | Values |
|---|---|
| `--group-by` | `auto` (default): folders, or nested tags for a vault with no folders. `folder`. `tag`: limbs from nested tags (`#ml/retrieval`), untagged notes at the base. |
| `--color-by` | `group` (default): top-level folder or tag. `tag`: first tag. `links`: backlink count, pale to dark. |
| `--schematic` | Draw the layout with straight lines instead of growing wood. Fast at any size. |

`quilt` prints the colour legend and the depth budget for the chosen preset,
then writes the quilt with its view-count suffix. `--cast` sends it to a
running [Looking Glass Bridge](https://lookingglassfactory.com/software/looking-glass-bridge);
if Bridge isn't running, the quilt is still written. In `viz3d`, the **Cast to
Looking Glass** toolbar button sends the current view.

The tree is built on the fleet's shared growth engine
(`kg_utils.viz3d`) and light-field output
([quiltwright](https://github.com/Flux-Frontiers/quiltwright)), as in the other
KGRAG modules.

---

## MCP server

`vaultkg-mcp` serves one vault to any MCP client (Claude Code, Cursor, GitHub
Copilot, Claude Desktop). To serve a vault, add it to the client's `.mcp.json`:

```json
{
  "mcpServers": {
    "vaultkg": {
      "command": "vaultkg-mcp",
      "args": ["--vault", "/path/to/vault"]
    }
  }
}
```

| Tool | What it returns |
|---|---|
| `graph_stats` | Note, heading, tag and unresolved-link counts |
| `query_vault(q, k, hop)` | Semantic hits, expanded along their links, as JSON |
| `pack_vault(q, k, hop, max_nodes)` | The same search with note and section text, as Markdown |
| `get_node(node_id)` | One node and its metadata (title, tags, aliases, dates) |
| `note_links(node_id, direction, rel, limit)` | Outgoing links, or backlinks with `direction="in"` |
| `analyze_vault` | The graph-health report |
| `snapshot_list`, `snapshot_show`, `snapshot_diff` | Saved metric snapshots |

Out-of-range arguments are rejected with a message naming the range, never
clamped: `k` 1-100, `hop` 0-5, `max_nodes` and `limit` 1-500. The server
closes the graph when it stops.

| Option | Meaning |
|---|---|
| `--vault DIR` | Vault root (default: the current directory). `--repo` is accepted as an alias. |
| `--db PATH` | Graph database (default: `<vault>/.vaultkg/graph.sqlite`) |
| `--transport {stdio,sse}` | MCP transport (default: `stdio`) |

Build the vault before you start the server. The server doesn't build it, and
exits with an error if `<vault>/.vaultkg/graph.sqlite` doesn't exist.

---

## Use VaultKG from KGRAG

KGRAG registers a vault as kind `vault`:

```bash
kgrag register my-brain vault ~/brain
```

`kgrag scan --auto-register` finds and registers any vault holding a
`.vaultkg/` store. KGRAG needs `vault-kg` installed in the same environment;
until it is, the adapter reports the KG as unavailable.

---

## Development

```bash
env -u VIRTUAL_ENV -u POETRY_ACTIVE poetry install --with dev --all-extras
env -u VIRTUAL_ENV -u POETRY_ACTIVE poetry run pytest --cov
env -u VIRTUAL_ENV -u POETRY_ACTIVE .venv/bin/pre-commit run --all-files
```

The tests embed with a hashing stub, so they need no model download. The
coverage floor is set in `pyproject.toml`.

---

## License

[Elastic License 2.0](https://www.elastic.co/licensing/elastic-license) -- see
[LICENSE](https://github.com/Flux-Frontiers/vault_kg/blob/main/LICENSE).

Free to use, modify, and distribute. You may not offer the software as a hosted
or managed service to third parties. Commercial internal use is permitted.

---

## Citation

If you use VaultKG in your research or project, please cite it:

> Suchanek, E. G. (2026). *VaultKG: Obsidian Vaults as Knowledge Graphs* (Version 0.1.0) [Software]. Flux-Frontiers. https://doi.org/10.5281/zenodo.22907544

```bibtex
@software{suchanek_vaultkg,
  author    = {Suchanek, Eric G.},
  title     = {{VaultKG}: Obsidian Vaults as Knowledge Graphs},
  version   = {0.1.0},
  year      = {2026},
  publisher = {Flux-Frontiers},
  url       = {https://github.com/Flux-Frontiers/vault_kg},
  doi       = {10.5281/zenodo.22907544},
}
```

See the [changelog](https://github.com/Flux-Frontiers/vault_kg/blob/main/CHANGELOG.md) for release history.
