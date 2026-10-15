# Release Notes -- v0.4.0

> Released: 2026-10-14

Rebuilding a vault after an edit is now quick. `vaultkg build` still rebuilds
the whole graph from the notes on disk, but it re-embeds only the notes and
sections whose text changed instead of every note.

## What changed

**Incremental embedding.** `vaultkg build` calls the SDK's new
`KGModule.sync()`. Each note and section's index text is compared with what
was embedded last time; only new or changed text is embedded, and the vectors
of deleted notes are removed. The graph itself is rebuilt in full, so the
same vault still always gives the same graph. On a 310-note vault, an
unchanged rebuild took 2.8 seconds and embedded nothing, against 8.2 seconds
for the first build.

**`--full` for the old behavior.** `vaultkg build --full` re-embeds every note,
as every build did before. The first build of a vault, and the first after a
`--full` build, embeds everything once either way.

**Current SDK.** VaultKG now requires kgmodule-utils 0.27.0, which provides
`sync()`.

## Upgrading

```bash
uv tool install --force --refresh "vault-kg[semantic,viz,viz3d]==0.4.0"
```

Nothing else changes. The next `vaultkg build` embeds everything once while
it records what it embedded; builds after that are incremental.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
