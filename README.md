[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: Elastic-2.0](https://img.shields.io/badge/License-Elastic%202.0-blue.svg)](https://www.elastic.co/licensing/elastic-license)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/Flux-Frontiers/vault_kg/releases)
[![CI](https://github.com/Flux-Frontiers/vault_kg/actions/workflows/ci.yml/badge.svg)](https://github.com/Flux-Frontiers/vault_kg/actions/workflows/ci.yml)
[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)

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

> **Status: alpha (0.1.0).** Build, link resolution, graph-health analysis,
> query and pack, snapshots, the `vaultkg` CLI and the `vaultkg-mcp` server work
> end to end, and have been run against a 250-note vault. The KGRAG adapter
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

```bash
pip install "vault-kg[semantic]"
```

The `semantic` extra adds the embedding model and vector index for `query`,
`pack` and the matching MCP tools. Without it, everything else works; build with
`--no-index`.

To work on VaultKG, install from a clone:

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
vaultkg links --vault ~/brain --in "wiki/Retrieval"    # backlinks
vaultkg snapshot save --vault ~/brain
```

- `build --no-index` skips embeddings. `analyze`, `stats` and `links` work without them.
- `--exclude PATTERN` (repeatable) skips folders such as `templates` or `raw`.
  Dot-folders (`.obsidian/`, `.trash/`, `.vaultkg/`) are always skipped.
- A note can be named by its node id (`note:wiki/Retrieval.md`) or its vault
  path, with or without `.md`.

Obsidian ignores dot-folders, so the `.vaultkg/` store never shows up as a note.

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
supports the `stdio` (default) and `sse` transports, and closes the graph when
it stops.

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

> Suchanek, E. G. (2026). *VaultKG: Obsidian Vaults as Knowledge Graphs* (Version 0.1.0) [Software]. Flux-Frontiers. https://github.com/Flux-Frontiers/vault_kg

```bibtex
@software{suchanek_vaultkg,
  author    = {Suchanek, Eric G.},
  title     = {{VaultKG}: Obsidian Vaults as Knowledge Graphs},
  version   = {0.1.0},
  year      = {2026},
  publisher = {Flux-Frontiers},
  url       = {https://github.com/Flux-Frontiers/vault_kg},
}
```

See the [changelog](https://github.com/Flux-Frontiers/vault_kg/blob/main/CHANGELOG.md) for release history.
