# Graph health

`vaultkg analyze` reports the vault's structure, computed from the graph with
plain graph algorithms: degree counts, connected components and articulation
points. No model reads the notes, so the same build always gives the same
report.

The note graph used here collapses a link to a heading onto its note, and
ignores `CONTAINS` and `TAGGED`: two notes are linked when one links to,
embeds or typed-links the other.

## What it reports

| Section | What it lists |
|---|---|
| Hubs | Notes the most other notes link to |
| Bridges | Notes whose removal would split the graph: the only path between two groups |
| Wanted pages | Link targets with no note, ranked by how many notes link to them |
| Orphans | Notes with no links in or out |
| Islands | Linked groups cut off from the largest one |
| Typed links | Count per relation, and every `CONTRADICTS` pair |
| Tags | The most-used tags |
| Warnings | Ambiguous links, and frontmatter that failed to parse |

On the seven-note vault used in these pages, the report begins:

```text
# VaultKG Analysis

7 notes, 9 note-to-note links, 1 linked group (largest 6), 1 orphans, 2 wanted pages.

## Hubs

Most-linked notes, by distinct notes linking in.

1. Retrieval augmented generation (`wiki/concepts/Retrieval.md`) -- 4
1. Search (`wiki/concepts/Search.md`) -- 2
...

## Wanted pages

Link targets no note answers to.

- `long context replaces rag` -- linked from 1
- `nowhere` -- linked from 1
```

`vaultkg analyze --json` prints the same figures as JSON, for scripts.

## Track it over time

A snapshot records the health figures and graph counts at one moment:

```bash
vaultkg snapshot save --vault ~/brain v1          # KEY defaults to a UTC timestamp
vaultkg snapshot list --vault ~/brain
vaultkg snapshot diff --vault ~/brain v1 v2
```

```text
v1                               notes      7  links       9  orphans     1  wanted     2
```

`snapshot save` skips a save when nothing changed since the last snapshot;
`--force` saves anyway. `snapshot diff` reports the change in every figure
between two snapshots, so you can see whether a week of writing added links
or only notes. Snapshots are small JSON files under `.vaultkg/snapshots/`,
worth keeping in version control.
