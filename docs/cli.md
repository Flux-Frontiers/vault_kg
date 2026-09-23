# Command reference

Every `vaultkg` command, with its options and defaults. For what the graph
holds, see [What the graph holds](graph.md); for the views, see
[Seeing the vault](visualization.md). This page is the place to look up a flag.

Every command takes `--vault DIRECTORY` (default: the current directory) and
`--help`. `vaultkg --version` prints the installed version.

Some commands need an extra installed:

| Extra | Needed by |
|---|---|
| `semantic` | `build` without `--no-index`, `query`, `pack` |
| `viz` | `viz` |
| `viz3d` | `quilt`, `viz3d` |

A command that needs a missing extra stops and names the `pip install` line.
Commands that read the graph say so when the vault hasn't been built.

A NODE argument is a node id (`note:wiki/Retrieval.md`,
`heading:wiki/Retrieval.md#failure-modes`, `tag:ml/retrieval`) or a note's
vault path, with or without `.md` (`wiki/Retrieval`). Backticks and quotes
around it are stripped.

## Build and inspect

### `vaultkg build`

Parse the vault into a graph and a vector index, in `<vault>/.vaultkg/`.

| Option | Meaning |
|---|---|
| `--exclude PATTERN` | Folder name or glob on vault-relative paths to skip. Repeatable. Dot-folders are always skipped |
| `--no-index` | Build the graph only. Removes an existing vector index, which would no longer match |
| `--wipe / --no-wipe` | Rebuild from scratch. Default `--wipe`; `--no-wipe` never removes deleted notes |

```bash
vaultkg build --vault ~/brain --exclude templates --exclude raw
```

### `vaultkg stats`

Print node and edge counts as JSON: `total_nodes`, `total_edges`,
`node_counts`, `edge_counts`, and `notes`, `headings`, `tags` and
`unresolved`. No options.

### `vaultkg analyze`

Print the graph-health report: hubs, bridges, wanted pages, orphans, islands,
typed links, tags and warnings. See [Graph health](health.md).

| Option | Meaning |
|---|---|
| `--json` | Print the health figures as JSON instead |

## Search

### `vaultkg query Q`

Semantic search over notes and sections, then expansion along their links.
Each line is `score  hop  kind  id`.

| Option | Meaning |
|---|---|
| `-k INTEGER` | Seed hits, 1-100. Default 8 |
| `--hop INTEGER` | Link hops to expand, 0-5. Default 1; 0 returns the semantic hits only |
| `--json` | Print the full result, nodes and the edges among them, as JSON |

```bash
vaultkg query --vault ~/brain "why do long contexts fail" -k 3
```

### `vaultkg pack Q`

The same search, printed as Markdown with each note's or section's text and
its vault path and line span. Takes `-k` and `--hop` as `query` does.

## Links

### `vaultkg links NODE`

What NODE links to; with `--in`, what links to it. A note's backlinks include
links to its sections, marked with the section they land on. See
[Links and backlinks](graph.md#links-and-backlinks).

| Option | Meaning |
|---|---|
| `--in` | Backlinks instead of outgoing links |
| `--rel TEXT` | Only this relation, such as `LINKS_TO` or `SUPPORTS` (case-insensitive) |
| `--limit INTEGER` | Links listed, 1-500. Default 50 |

```bash
vaultkg links --vault ~/brain --in wiki/concepts/Retrieval
vaultkg links --vault ~/brain wiki/concepts/Retrieval --rel supports
```

## Snapshots

### `vaultkg snapshot save [KEY]`

Record the current health figures and counts under KEY, a release tag or a
name. KEY defaults to a UTC timestamp.

| Option | Meaning |
|---|---|
| `--force` | Save even if nothing changed since the last snapshot |

### `vaultkg snapshot list`

List snapshots, newest first, with notes, links, orphans and wanted pages.
No options.

### `vaultkg snapshot diff A B`

Compare snapshots A and B, as JSON: both sets of figures and the change in
each. No options.

## Views

### `vaultkg viz [ROOT]`

Write the link graph as one self-contained interactive HTML page. With ROOT,
the page shows that node's neighbourhood; without it, the most connected part
of the vault. Needs the `viz` extra. See [The link graph](visualization.md#the-link-graph).

| Option | Meaning |
|---|---|
| `-o, --output FILE` | Page to write. Default `<vault name>_links.html` in the current directory |
| `--hops INTEGER` | Links to expand from ROOT, 0-5. Default 1 |
| `--max-nodes INTEGER` | Node budget, 2-5000. Default 200 |
| `--headings` | Draw headings as well as notes |
| `--edge-labels` | Print each link's relation on the canvas. Default: on hover only |

### `vaultkg quilt`

Grow the vault as a 3-D tree and render it as a Looking Glass quilt. Needs the
`viz3d` extra. See [The vault as a tree](visualization.md#the-vault-as-a-tree).

| Option | Meaning |
|---|---|
| `--preset TEXT` | Looking Glass quilt preset. Default `16-landscape` |
| `-o, --out DIRECTORY` | Output directory. Default `renders` |
| `--group-by [auto\|folder\|tag]` | Limbs from folders, or from nested tags. Default `auto`: tags only for a vault with no folders |
| `--color-by [group\|tag\|links]` | Leaf colour by top-level group, first tag, or backlink count. Default `group` |
| `--size-by [links\|none]` | Leaf size by backlink count, or all one size. Default `links` |
| `--tip-radius FLOAT` | Twig radius, in world units. Default 0.06 |
| `--leaf-size FLOAT` | Leaf radius. Default 0.35 |
| `--zoom FLOAT` | Camera dolly after framing; above 1 fills more of the tile. Default 1.0 |
| `--fov FLOAT` | Per-view vertical field of view, in degrees. Default 14.0 |
| `--cast` | Send the finished quilt to Looking Glass Bridge |
| `--schematic` | Draw the layout with straight lines instead of growing wood |

The quilt is named `<vault name>_qs<columns>x<rows>a<aspect>.png`, the suffix
Looking Glass software reads its layout from.

### `vaultkg viz3d`

Open the 3-D tree in an interactive viewer, with a Cast to Looking Glass
button. Needs the `viz3d` extra.

| Option | Meaning |
|---|---|
| `--group-by`, `--color-by`, `--size-by`, `--preset`, `--schematic` | As for `quilt` |
| `--width INTEGER` | Window width in pixels. Default 1400 |
| `--height INTEGER` | Window height in pixels. Default 900 |

## The MCP server

### `vaultkg-mcp`

A separate command that serves one built vault to MCP clients. See
[MCP server](mcp.md).

| Option | Meaning |
|---|---|
| `--vault DIRECTORY` | Vault root. Default `.`; `--repo` is an alias |
| `--db PATH` | Graph database. Default `<vault>/.vaultkg/graph.sqlite` |
| `--transport [stdio\|sse]` | MCP transport. Default `stdio` |
