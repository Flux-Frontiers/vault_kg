# What the graph holds

Everything in the graph is parsed from the notes: frontmatter is YAML, a
heading is an ATX `#` line, a link is `[[...]]` or `[...](x.md)`. Nothing is
inferred from prose, so every edge is one the author wrote.

## Nodes

| Kind | Id | From |
|---|---|---|
| `note` | `note:<path>` | every `.md` file |
| `heading` | `heading:<path>#<slug>` | every ATX heading, as a section with its line span |
| `tag` | `tag:<tag>` | `#tag` and frontmatter `tags:`; nested tags chain (`#ml` -> `#ml/retrieval`) |
| `attachment` | `attachment:<path>` | an embedded or linked non-Markdown file |
| `symbol` | `missing:<target>` | a link target no file answers to (Obsidian's "unresolved links") |

A repeated heading in one note gets a numbered id (`#notes`, `#notes~2`), so
two builds of the same vault always produce the same ids. Missing targets are
kept out of search results; they are gaps in the vault, not notes.

## Edges

| Relation | From |
|---|---|
| `LINKS_TO` | `[[Page]]`, `[[Page\|alias]]`, `[text](page.md)`, `[text](folder/)` |
| `EMBEDS` | `![[Page]]`, `![[image.png]]` |
| `CONTAINS` | note -> heading -> subheading, tag -> nested tag |
| `TAGGED` | note -> tag |
| typed | Dataview inline fields (`(supports:: [[X]])`, `- up:: [[Home]]`) and frontmatter keys holding wikilinks (`contradicts: ["[[Y]]"]`) |

A typed link's key becomes its relation, upper-cased: `supports::` is
`SUPPORTS`, a frontmatter `extends:` key is `EXTENDS`. Any key works, so a
vault's own vocabulary becomes its relations. Frontmatter keys that describe
the note itself (`aliases`, `tags`, `title`, `type`, `cssclasses`, `publish`)
are never read as links.

Repeated links between the same two nodes with the same relation are one edge.
Its evidence records how many times the link was written, the lines it was
written on, and the aliases it was written with.

## How links resolve

Links resolve the way Obsidian resolves them, in this order:

1. The exact vault path.
2. A path relative to the linking note.
3. The file name, in the same folder first, then the shortest path.
4. A frontmatter `aliases` entry.

- `[[Page#Heading]]` points at the heading, when the note has one by that
  name.
- A Markdown link is a path, relative to the note or to the vault root, and
  never resolves by name.
- A link that matched several same-named notes is marked `ambiguous`, and
  `analyze` counts those links. Link by path to make one exact.
- Wikilinks inside fenced code, inline code and `%% comments %%` are ignored.
- Names are compared case-insensitively and Unicode-normalized, so
  `[[Café]]` finds `Café.md` on macOS, which stores names decomposed.

## Links and backlinks

`vaultkg links` lists what a node links to:

```bash
vaultkg links --vault ~/brain wiki/concepts/Retrieval
```

```text
CONTAINS     -> heading:wiki/concepts/Retrieval.md#retrieval-augmented-generation
EMBEDS       -> attachment:assets/diagram.png
EXTENDS      -> note:wiki/concepts/Search.md
LINKS_TO     -> missing:nowhere
LINKS_TO     -> note:wiki/concepts/Search.md
SUPPORTS     -> note:wiki/sources/Lost in the Middle.md
TAGGED       -> tag:core
...
```

With `--in` it lists what links to it. A note's backlinks include links to
any of its sections, as in Obsidian, and name the section:

```bash
vaultkg links --vault ~/brain --in wiki/concepts/Retrieval
```

```text
LINKS_TO     <- note:index.md
LINKS_TO     <- note:wiki/concepts/Search.md  (#failure-modes)
LINKS_TO     <- note:wiki/sources/Lost in the Middle.md
LINKS_TO     <- note:wiki/sources/Search.md
```

`--rel SUPPORTS` narrows either list to one relation.

## Dates

Frontmatter `date` becomes the fleet's `occurred_start`, and `created`
becomes `recorded_at`, so KGRAG time-scoped queries can filter notes by date.
File modification times are not used, because they change on every clone.
