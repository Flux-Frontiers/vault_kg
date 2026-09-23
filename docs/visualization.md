# Seeing the vault

VaultKG draws a vault two ways: as a link graph you explore in a browser, and
as a 3-D tree grown from its folders, for the screen or a Looking Glass
display. Both are built on the fleet's shared visualization stack.

## The link graph

`vaultkg viz` writes one self-contained HTML page. It opens from disk in any
browser, with no server. Needs the `viz` extra.

```bash
vaultkg viz --vault ~/brain                             # the most connected part of the vault
vaultkg viz --vault ~/brain wiki/Retrieval --hops 2     # one note's neighbourhood
```

| Mark | Meaning |
|---|---|
| Dot | A note, sized by backlinks and coloured by its top-level folder |
| Gold ring | The root note, when you give one |
| Diamond | A tag |
| Square | An attachment |
| Grey triangle | A missing note: a link target no file answers to |
| Edge colour | The relation: blue for links, purple for embeds, green `SUPPORTS`, red `CONTRADICTS`, orange for other typed links. Hover an edge for its name; `--edge-labels` prints every relation on the canvas |

- With a root, the page shows everything within `--hops` links of it, in
  either direction, nearest first. Without one, it shows the `--max-nodes`
  nodes with the most edges.
- Headings are left out unless you pass `--headings`. A vault has several
  per note, and they hide the links between notes.
- Drag to pan, scroll to zoom, and click a node for its path, tags and text.

The page is drawn by `kg_utils.viz.build_graph_html`, the renderer every
fleet module shares; VaultKG supplies the colours, shapes and which nodes to
draw.

## The vault as a tree

`vaultkg quilt` and `vaultkg viz3d` grow the vault as a 3-D tree. Needs the
`viz3d` extra.

- The vault is the trunk.
- Each top-level folder is a limb; subfolders branch off their parent's limb,
  higher and further out.
- Every note is a leaf, clustered at the tip of the folder that holds it.
- Notes at the vault root ring the base of the trunk.

A bigger folder grows a longer limb, and a more linked note grows a bigger leaf. The wood is grown toward the leaves by
space colonization, seeded from the vault's name, so the same vault always
grows the same tree.

```bash
vaultkg viz3d --vault ~/brain                         # interactive: drag to orbit, scroll to zoom
vaultkg quilt --vault ~/brain                         # writes renders/brain_qs8x6a1.77778.png
vaultkg quilt --vault ~/brain --color-by links --cast
```

### Grouping and colour

| Option | Values |
|---|---|
| `--group-by` | `auto` (default): folders, or nested tags for a vault with no folders. `folder`. `tag`: limbs from nested tags (`#ml/retrieval` is limb `ml`, branch `retrieval`), untagged notes at the base |
| `--color-by` | `group` (default): top-level folder or tag. `tag`: first tag. `links`: backlink count, pale for none to dark for a hub |
| `--size-by` | `links` (default): a note's leaf grows with its backlinks, from 0.6x the base size for an unlinked note to at most 2.5x for a hub. `none`: every leaf one size |
| `--schematic` | Draw the layout with straight lines instead of growing wood. Fast at any size, and shows the layout the organic tree grows toward |

Colours come from the Okabe-Ito palette, which stays distinguishable under
the common forms of colour-vision deficiency. Groups past the seventh share
grey, so two unrelated folders never look alike. `quilt` prints the legend:

```text
Scene: brain (schematic, by folder) | notes=7  limbs=5
Legend: wiki #E69F00, (vault root) #56B4E9, projects #009E73
```

### Looking Glass

`quilt` frames the tree with the fleet's shared camera rule, which keeps the
whole tree in view from every angle of the display's view cone, then prints
the depth budget: how far the nearest and farthest leaves sit from the focal
plane, and their disparity between adjacent views.

```text
  focal plane      115.6 units
  view cone        50.0 deg over 48 views
```

It then renders every view and writes the quilt, named with the
`_qs<columns>x<rows>a<aspect>` suffix Looking Glass software reads. `--cast`
sends it to a running
[Looking Glass Bridge](https://lookingglassfactory.com/software/looking-glass-bridge);
if Bridge isn't running, the quilt is still written. In `viz3d`, the **Cast to
Looking Glass** toolbar button sends the current view.

- `--preset` picks the display; the presets are quiltwright's
  (`16-landscape`, `16-portrait`, `27-landscape`, `32-landscape`, `go`,
  `portrait`, and others).
- `--zoom` above 1 fills more of each view. The default leaves room for the
  whole view cone, so the tree can look small on a flat screen.

The growth engine is `kg_utils.viz3d`, and quilts are rendered by
[quiltwright](https://github.com/Flux-Frontiers/quiltwright). VaultKG supplies
only the grammar: which folder becomes which limb, and where each note grows.
