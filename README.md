# VaultKG

**VaultKG** turns an Obsidian-style Markdown vault into a fleet knowledge graph.

*Author: Eric G. Suchanek, PhD · Flux-Frontiers*

---

A vault already is a graph: pages are nodes, `[[wikilinks]]` are edges, and
people who keep typed links (`supports:: [[X]]`) have written down what kind of
edge. VaultKG reads that structure directly. It doesn't use a language model to
extract entities or guess relations, so every edge in the graph is one the
author actually wrote, and the same vault always builds the same graph.

Embeddings are used only to find entry points for a search. Everything after
that follows the stored links, as in the rest of the
[KGRAG](https://github.com/Flux-Frontiers/KGRAG) fleet.

## What becomes the graph

| Node | From |
|---|---|
| `note` | every `.md` file (dot-folders such as `.obsidian/` are skipped) |
| `heading` | every ATX heading, as a section with its line span |
| `tag` | `#tag`, frontmatter `tags:`; nested tags chain (`#ml` → `#ml/retrieval`) |
| `attachment` | an embedded or linked non-Markdown file |
| unresolved | a link target no file answers to (Obsidian's "unresolved links") |

| Edge | From |
|---|---|
| `LINKS_TO` | `[[Page]]`, `[[Page\|alias]]`, `[text](page.md)`, `[text](folder/)` |
| `EMBEDS` | `![[Page]]`, `![[image.png]]` |
| `CONTAINS` | note → heading → subheading, tag → nested tag |
| `TAGGED` | note → tag |
| typed | Dataview inline fields `(supports:: [[X]])`, `- up:: [[Home]]`, and frontmatter keys holding wikilinks (`contradicts: ["[[Y]]"]`), which become `SUPPORTS`, `UP`, `CONTRADICTS`... |

Links resolve the way Obsidian resolves them: exact path, then relative path,
then file name (same folder first, then the shortest path), then frontmatter
`aliases`. `[[Page#Heading]]` points at the heading. Wikilinks inside code
blocks, inline code and `%% comments %%` are ignored. A link that matched
several same-named notes is marked `ambiguous`.

Frontmatter `date` becomes the fleet's `occurred_start` and `created` becomes
`recorded_at`, so KGRAG time-scoped queries can filter notes by date. File
modification times are not used, because they change on every clone.

## Use

```bash
pip install -e ".[semantic]"        # or "." for build + analyze only

vaultkg build --vault ~/brain        # writes ~/brain/.vaultkg/
vaultkg analyze --vault ~/brain      # graph-health report
vaultkg query --vault ~/brain "why long contexts fail"
vaultkg pack  --vault ~/brain "why long contexts fail"
vaultkg snapshot save --vault ~/brain
```

`build --no-index` skips embeddings; `analyze` and `stats` work without them.
`--exclude PATTERN` (repeatable) skips folders such as `templates` or `raw`.

## Graph health

`vaultkg analyze` reports, computed from the graph alone:

- **Hubs**: the notes that the most other notes link to
- **Bridges**: notes whose removal would split the graph (articulation points)
- **Wanted pages**: link targets with no note, ranked by how many notes want them
- **Orphans**: notes with no links in or out
- **Islands**: linked groups cut off from the main graph
- **Typed links**: counts per relation, with every `contradicts` pair listed
- **Tags**, **ambiguous links**, and **frontmatter that failed to parse**

## In KGRAG

KGRAG registers a vault as kind `vault`:

```bash
kgrag registry add my-brain ~/brain --kind vault
```
