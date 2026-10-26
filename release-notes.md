# Release Notes -- v0.6.0

> Released: 2026-10-26

VaultKG's MCP server now runs on the fleet's shared base, `kg_utils.mcp`, so
its first five tools have the same names on every fleet KG server: `stats`,
`query`, `pack`, `get_node` and `neighbors`. `note_links`, `analyze_vault` and
the snapshot tools keep their names. Existing `vaultkg-mcp --vault` configs
keep working.

## What changed

**Canonical tool names.** `graph_stats` is `stats`, `query_vault` is `query`
and `pack_vault` is `pack`, with no aliases. The new `neighbors` tool walks a
node's links in either direction and, like `get_node`, takes a note's vault
path as well as its id. A missing node is now a tool error from `get_node`
rather than `null`.

**One command, standard flags.** `vaultkg mcp` takes the fleet's `--repo`,
`--db`, `--vectors`, `--model`, `--transport stdio|streamable-http`, `--host`,
`--port` and `--manifest`. `vaultkg-mcp` is the same command and still
accepts `--vault` (and `--vault=PATH`) for `--repo`. The graph opens per
session and closes after, and an unbuilt vault is refused instead of served
empty.

**Statistics in the fleet shape.** `VaultKG.stats()` returns `kind`, `nodes`
(`total`, `by_kind`) and `edges` (`total`, `by_rel`), plus `meaningful_nodes`
and the note, heading, tag and unresolved-link counts.

**Fixed:** against kgmodule-utils 0.29.0 the note, heading and tag counts read
0 and the analysis report printed empty counts tables. Both read the new
shape now.

## Upgrading

Rename the tools in agent instructions and scripts (`graph_stats` -> `stats`,
`query_vault` -> `query`, `pack_vault` -> `pack`) and drop `--transport sse`
from any config. Code that read `VaultKG.stats()["node_counts"]` reads
`["nodes"]["by_kind"]` instead. vault-kg now needs kgmodule-utils 0.29.0, whose
`[mcp]` extra brings the MCP SDK.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
