# Release Notes -- v0.2.0

> Released: 2026-09-22

This release makes the vault's structure easier to read at a glance. In the
3-D tree, a note's leaf now grows with the number of notes that link to it,
so the hubs of a vault stand out without reading a label. In the 2-D link
graph, relations move off the canvas and onto hover, which keeps a note's
neighbourhood legible when nearly every edge is a plain link.

## What changed

**Leaves sized by backlinks.** `vaultkg quilt` and `vaultkg viz3d` size each
leaf by its note's backlinks: an unlinked note is 0.6 times the base size,
one backlink is 1.0 times, and hubs grow with the square root of their count
up to 2.5 times. `--size-by none` draws every leaf one size. Both the organic
and the schematic renders honour it.

**Edge labels on hover.** `vaultkg viz` no longer prints each relation across
the canvas; it shows it on hover and in the edge colour. `--edge-labels`
prints them all again.

**A newer SDK.** VaultKG now requires kgmodule-utils 0.24.0, which added both
rendering options and a way to drop a stale vector index. `vaultkg build
--no-index` removes an index from an earlier build through the SDK rather
than deleting the files itself; what it does is unchanged.

## Upgrading

```bash
uv tool upgrade vault-kg --reinstall
```

No rebuild is needed; existing `.vaultkg/` stores work as they are. To keep
the previous look, pass `--size-by none` to `quilt` and `viz3d` and
`--edge-labels` to `viz`. KGRAG federates vaults from kg-rag 0.17.0, with the
`kg-rag[vault]` extra.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
