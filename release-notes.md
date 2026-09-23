# Release Notes -- v0.1.0

> Released: 2026-09-22

VaultKG turns an Obsidian-style Markdown vault into a knowledge graph built
from the links its author wrote. Notes, sections, tags and attachments become
nodes; wikilinks, embeds, tags and typed links such as `supports:: [[X]]`
become edges. Nothing is extracted by a language model, so the same vault
always builds the same graph, and every edge can be traced to the line it
was written on. This first release covers building, searching, analysing and
viewing a vault, and serving it to agents.

## What's in it

**A graph that follows Obsidian's rules.** Links resolve the way Obsidian
resolves them: by path, then by file name, then by alias, with section
anchors pointing at the heading and ambiguous matches flagged rather than
guessed. Typed links, from Dataview inline fields or frontmatter keys, keep
their own relation names, so a vault's own vocabulary (`SUPPORTS`,
`CONTRADICTS`, `UP`) becomes part of the graph.

**Search that stays grounded.** `vaultkg query` uses embeddings only to find
where to start, then follows stored links from there; `vaultkg pack` returns
the matching notes and sections with their paths and line numbers, ready to
hand to a model. `vaultkg links` answers what a note links to and what links
back to it, section links included.

**The vault's structure, measured.** `vaultkg analyze` reports hubs, bridges,
wanted pages, orphans and islands from the graph alone, and snapshots record
those figures so you can compare a vault's shape over time.

**Views.** `vaultkg viz` writes the link graph as one interactive HTML page,
with notes sized by backlinks and coloured by folder. `vaultkg quilt` and
`vaultkg viz3d` grow the vault as a 3-D tree, its folders as limbs and its
notes as leaves, for the screen or a Looking Glass display.

**For agents.** `vaultkg-mcp` serves a vault to Claude Code, Cursor or any
MCP client, with bounded, validated arguments. KGRAG can federate a vault
with code, documents and its other knowledge graphs through its `vault`
kind, which ships in KGRAG's next release.

## Installing

```bash
uv tool install "vault-kg[semantic,viz,viz3d]"
vaultkg build --vault ~/brain
```

The core install builds, analyses and serves a vault. The `semantic` extra
adds search, `viz` the link graph, and `viz3d` the 3-D views. The
documentation is at https://flux-frontiers.github.io/vault_kg/.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
