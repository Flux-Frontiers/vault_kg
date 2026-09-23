# Using VaultKG from KGRAG

[KGRAG](https://github.com/Flux-Frontiers/KGRAG) federates knowledge graphs:
one query searches code, documents, diaries, connectomes and vaults together.
It registers a vault as kind `vault`.

```bash
vaultkg build --vault ~/brain
kgrag register my-brain vault ~/brain
kgrag query "why do long contexts fail"
```

`kgrag scan --auto-register` finds and registers every directory holding a
`.vaultkg/` store.

KGRAG loads VaultKG through its `vault` adapter, so `vault-kg` must be
installed in the same environment as `kg-rag`. Until it is, KGRAG lists the
vault as unavailable rather than failing. The `vault` kind ships in kg-rag
0.17.0; `pip install "kg-rag[vault]"` installs both.

## What KGRAG sees

- Hits carry the note's vault path and line span, so a federated answer
  cites the exact section it came from.
- Notes with frontmatter `date` or `created` carry the fleet's
  `occurred_start` and `recorded_at` keys, so a KGRAG query scoped to a time
  range filters vault notes with everything else.
- KGRAG's `stats` for a vault adds its note, heading, tag and
  unresolved-link counts to the standard envelope.
