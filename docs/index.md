# VaultKG

**Obsidian-style Markdown vaults as knowledge graphs. Every edge is a link the author wrote.**

*Eric G. Suchanek, PhD -- Flux-Frontiers*

A vault already is a graph: pages are nodes, `[[wikilinks]]` are edges, and
people who keep typed links (`supports:: [[X]]`) have written down what kind of
edge. VaultKG reads that structure directly. It doesn't use a language model to
extract entities or guess relations, so the same vault always builds the same
graph.

Embeddings are used only to find entry points for a search. Everything after
that follows the stored links, as in the rest of the
[KGRAG](https://github.com/Flux-Frontiers/KGRAG) fleet. VaultKG is a `KGModule`
built on [kgmodule-utils](https://github.com/Flux-Frontiers/KG_utils).

## What you can do with it

- **Search a vault by meaning, then follow its links.** `vaultkg query` finds
  the notes and sections closest to a question and expands along the links
  from them; `vaultkg pack` returns their text for an LLM. See
  [Install and build a vault](getting-started.md).
- **Ask what links to what.** `vaultkg links` lists a note's links or its
  backlinks, including typed ones such as `SUPPORTS` and `CONTRADICTS`. See
  [What the graph holds](graph.md).
- **Check the vault's structure.** `vaultkg analyze` reports hubs, bridges,
  wanted pages, orphans and islands, and snapshots track them over time. See
  [Graph health](health.md).
- **See it.** `vaultkg viz` draws the link graph as an interactive page;
  `vaultkg quilt` and `vaultkg viz3d` grow the vault as a 3-D tree, for the
  screen or a Looking Glass display. See [Seeing the vault](visualization.md).
- **Give it to an agent.** `vaultkg-mcp` serves the vault to Claude Code,
  Cursor or any MCP client, and KGRAG federates it with code, documents and
  other knowledge graphs. See [MCP server](mcp.md) and
  [Using VaultKG from KGRAG](kgrag.md).

## Quick start

```bash
uv tool install "vault-kg[semantic,viz,viz3d]"

vaultkg build --vault ~/brain
vaultkg query --vault ~/brain "why do long contexts fail"
vaultkg links --vault ~/brain --in wiki/Retrieval
vaultkg analyze --vault ~/brain
vaultkg viz --vault ~/brain
```

Every command is listed with its options in the [CLI reference](cli.md).

!!! note "License"
    VaultKG is licensed under the
    [Elastic License 2.0](https://www.elastic.co/licensing/elastic-license).
    You may use, modify and distribute it, including for commercial internal
    use; you may not offer it to third parties as a hosted or managed service.
