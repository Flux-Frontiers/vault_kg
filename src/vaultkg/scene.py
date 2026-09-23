"""scene.py -- a vault grown as a 3-D tree, for the viewer and for quilts.

The grammar: the vault is the trunk, its folders are limbs (subfolders branch
off their parent folder's limb), and every note is a leaf clustered at the tip
of the folder that holds it. Notes at the vault root ring the base of the
trunk. The folder tree is structure the author built, so the canopy's shape
is the vault's own shape, and the same vault always grows the same tree.

A vault with no folders has nothing to branch on, so ``group_by="auto"``
grows it from nested tags instead (``#ml/retrieval`` is the limb
``ml`` -> ``retrieval``), with untagged notes at the base.

Split the way genealogy_kg's ``scene.py`` is, so placement is testable with
NumPy alone:

* :func:`vault_tree_positions` is pure NumPy: where each limb tip and each
  note goes. No PyVista import.
* :func:`build_vault_tree_scene` grows wood toward those points with the
  fleet's shared space-colonization engine (``kg_utils.viz3d``) and composes
  it into a caller's ``pv.Plotter``. That half needs the ``viz3d`` extra.

Colours come from :mod:`vaultkg.theme`, never from :mod:`vaultkg.viz`, so this
module imports with the ``viz3d`` extra alone.
"""

from __future__ import annotations

import math
import posixpath
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from kg_utils.viz3d import (
    fibonacci_annulus,
    grow_tree,
    leaf_facing,
    oriented_cluster,
    seed_from_key,
)

from vaultkg.analysis import vault_health
from vaultkg.theme import LINK_BUCKETS, OTHER_COLOR, ROOT_LABEL, category_colors, link_bucket

if TYPE_CHECKING:
    import pyvista as pv

    from vaultkg.module import VaultKG

#: Golden angle, in radians: even angular spacing for limbs with no natural
#: order around the trunk (the same spacing genealogy_kg and pycode_kg use).
GOLDEN_ANGLE: Final[float] = math.pi * (3.0 - math.sqrt(5.0))

#: Trunk height per level of folder nesting, floored so a one-level vault
#: still gets a real trunk to branch from.
TRUNK_HEIGHT_PER_LEVEL: Final[float] = 2.4
MIN_TRUNK_HEIGHT: Final[float] = 3.0

#: Height band limbs branch in, as fractions of trunk height: top-level
#: folders at the bottom of the band, the deepest subfolders at the top.
LIMB_LOW: Final[float] = 0.4
LIMB_HIGH: Final[float] = 0.95

#: Radial reach of a top-level limb tip, and of each further level, before
#: scaling by how many notes the folder holds.
BRANCH_REACH: Final[float] = 2.2
SUBBRANCH_REACH: Final[float] = 1.3
REACH_FLOOR: Final[float] = 0.4

#: Angular spread of sibling subfolders around their parent's direction.
SIBLING_SPREAD: Final[float] = 0.9

#: Growth-target guide points up the trunk, so colonization climbs before it
#: forks. Never drawn as foliage.
N_TRUNK_GUIDES: Final[int] = 8
TRUNK_GUIDE_TOP: Final[float] = 0.35

#: Height of the ring of root-level notes, as a fraction of trunk height.
ROOT_RING_HEIGHT: Final[float] = 0.12

#: Note count at which radii and reach are exactly the defaults; smaller
#: vaults scale up so a ten-note tree is not dust, larger ones scale down.
SIZE_REFERENCE_NOTES: Final[int] = 200
MIN_SIZE_SCALE: Final[float] = 0.6
MAX_SIZE_SCALE: Final[float] = 3.0

WOOD_COLOR: Final[str] = "#5A3A22"
TWIG_COLOR: Final[str] = "#8A6A4A"

GROUP_BY: Final[tuple[str, ...]] = ("auto", "folder", "tag")
COLOR_BY: Final[tuple[str, ...]] = ("group", "tag", "links")
SIZE_BY: Final[tuple[str, ...]] = ("links", "none")

#: Leaf size by backlinks, as a multiple of ``leaf_size``: an unlinked note
#: is 0.6x, one backlink 1.0x, and hubs grow with the square root of their
#: count up to 2.5x, so one very linked note cannot swamp the canopy.
LEAF_SCALE_BASE: Final[float] = 0.6
LEAF_SCALE_STEP: Final[float] = 0.4
LEAF_SCALE_MAX: Final[float] = 2.5


def _size_scale(n_notes: int) -> float:
    """Geometry scale: bigger for small vaults, smaller for large ones."""
    raw = math.sqrt(SIZE_REFERENCE_NOTES / max(n_notes, 1))
    return min(max(raw, MIN_SIZE_SCALE), MAX_SIZE_SCALE)


@dataclass
class VaultTreePositions:
    """Pure-geometry result of :func:`vault_tree_positions`.

    :param note_positions: Each note id's leaf position.
    :param limb_tips: Each group path's limb tip (``"wiki/concepts"``).
    :param limb_parent: Each group path's parent group (``""`` for top level).
    :param note_group: Each note's group path; ``""`` for notes at the base.
    :param trunk_guides: Growth targets up the trunk, never drawn.
    :param trunk_height: Trunk height used, in world units.
    :param group_by: ``"folder"`` or ``"tag"``, the grouping actually used.
    :param size_scale: Geometry multiplier for twig and leaf radii.
    """

    note_positions: dict[str, np.ndarray]
    limb_tips: dict[str, np.ndarray]
    limb_parent: dict[str, str]
    note_group: dict[str, str]
    trunk_guides: np.ndarray
    trunk_height: float
    group_by: str
    size_scale: float = 1.0


def _note_groups(notes: list[dict[str, Any]], group_by: str) -> tuple[dict[str, str], str]:
    """Each note's group path, and the grouping used.

    :param notes: Note nodes from the store.
    :param group_by: ``"auto"``, ``"folder"`` or ``"tag"``.
    :return: ``({note id: group path}, grouping used)``.
    :raises ValueError: On an unknown ``group_by``.
    """
    if group_by not in GROUP_BY:
        raise ValueError(f"group_by must be one of {', '.join(GROUP_BY)}, got {group_by!r}")
    folders: dict[str, str] = {
        str(n["id"]): posixpath.dirname(str(n.get("module_path") or "")) for n in notes
    }
    if group_by == "folder" or (group_by == "auto" and any(folders.values())):
        return folders, "folder"
    tags: dict[str, str] = {}
    for n in notes:
        first = ((n.get("metadata") or {}).get("tags") or [""])[0]
        tags[n["id"]] = str(first).strip("/")
    return tags, "tag"


def vault_tree_positions(
    notes: list[dict[str, Any]], *, group_by: str = "auto"
) -> VaultTreePositions:
    """Place every limb tip and every note.

    Each group path and all its ancestors become limbs. Top-level limbs are
    spread by the golden angle, largest (most notes beneath) first;
    subfolders fan out around their parent's direction and reach further and
    higher. Limb reach grows with the square root of the notes beneath it, so
    the biggest folder is the longest limb. Notes cluster at their own
    group's tip, in path order, facing out and up.

    :param notes: Note nodes (``id``, ``module_path``, ``metadata``).
    :param group_by: ``"auto"`` (folders, or nested tags for a flat vault),
        ``"folder"`` or ``"tag"``.
    :return: Positions for the whole tree.
    :raises ValueError: If there are no notes, or ``group_by`` is unknown.
    """
    if not notes:
        raise ValueError("the vault has no notes to grow")
    groups, used = _note_groups(notes, group_by)
    scale = _size_scale(len(notes))

    # Every group and each of its ancestors, with the notes beneath each.
    beneath: Counter[str] = Counter()
    for g in groups.values():
        parts = g.split("/") if g else []
        for d in range(1, len(parts) + 1):
            beneath["/".join(parts[:d])] += 1
    depth = {g: g.count("/") + 1 for g in beneath}
    max_depth = max(depth.values(), default=1)
    trunk_height = max(TRUNK_HEIGHT_PER_LEVEL * max_depth, MIN_TRUNK_HEIGHT)
    most = max(beneath.values(), default=1)

    def reach_weight(g: str) -> float:
        return REACH_FLOOR + (1.0 - REACH_FLOOR) * math.sqrt(beneath[g] / most)

    def height(d: int) -> float:
        frac = (d - 1) / max(max_depth - 1, 1)
        return trunk_height * (LIMB_LOW + (LIMB_HIGH - LIMB_LOW) * frac)

    def order(gs: list[str]) -> list[str]:
        return sorted(gs, key=lambda g: (-beneath[g], g))

    children: dict[str, list[str]] = {}
    for g in beneath:
        children.setdefault(posixpath.dirname(g), []).append(g)

    limb_tips: dict[str, np.ndarray] = {}
    limb_parent: dict[str, str] = {}
    angle: dict[str, float] = {}
    radius: dict[str, float] = {}
    for i, g in enumerate(order(children.get("", []))):
        angle[g] = i * GOLDEN_ANGLE
        radius[g] = BRANCH_REACH * scale * reach_weight(g)
    queue = order(children.get("", []))
    while queue:
        g = queue.pop(0)
        limb_parent[g] = posixpath.dirname(g)
        a, r = angle[g], radius[g]
        limb_tips[g] = np.array([r * math.cos(a), r * math.sin(a), height(depth[g])])
        kids = order(children.get(g, []))
        for k, c in enumerate(kids):
            offset = (k - (len(kids) - 1) / 2) * SIBLING_SPREAD / max(len(kids), 1)
            angle[c] = a + offset
            radius[c] = r + SUBBRANCH_REACH * scale * reach_weight(c)
        queue.extend(kids)

    note_positions: dict[str, np.ndarray] = {}
    by_group: dict[str, list[str]] = {}
    for nid in sorted(groups):
        by_group.setdefault(groups[nid], []).append(nid)
    for g, members in sorted(by_group.items()):
        if not g:
            continue
        tip = limb_tips[g]
        facing = leaf_facing(tip - np.array([0.0, 0.0, tip[2]]))
        cluster_radius = (0.9 + math.sqrt(len(members)) * 0.6) * scale
        for nid, pos in zip(
            members, oriented_cluster(len(members), tip, facing, cluster_radius), strict=True
        ):
            note_positions[nid] = pos

    base = by_group.get("", [])
    if base:
        # A flat ring above the ground, not a sphere: a sphere's lower half
        # would put notes underground.
        outer = max(BRANCH_REACH * scale * 0.5, 1.0)
        ring = fibonacci_annulus(
            len(base),
            inner_radius=outer * 0.3,
            outer_radius=outer,
            center=np.array([0.0, 0.0, trunk_height * ROOT_RING_HEIGHT]),
            z_thickness=trunk_height * 0.02,
        )
        for nid, pos in zip(base, ring, strict=True):
            note_positions[nid] = pos

    guide_z = np.linspace(trunk_height * 0.06, trunk_height * TRUNK_GUIDE_TOP, N_TRUNK_GUIDES)
    guides = np.column_stack([np.zeros_like(guide_z), np.zeros_like(guide_z), guide_z])
    return VaultTreePositions(
        note_positions=note_positions,
        limb_tips=limb_tips,
        limb_parent=limb_parent,
        note_group=groups,
        trunk_guides=guides,
        trunk_height=trunk_height,
        group_by=used,
        size_scale=scale,
    )


@dataclass
class VaultTree:
    """What a composed vault-tree scene contains.

    :param positions: The placement it was grown from.
    :param points: Every drawn point, for camera framing with
        :func:`~kg_utils.viz3d.frame_tree`.
    :param legend: Label to hex colour, for the CLI and window title.
    :param title: One-line summary.
    :param counts: ``{"notes": n, "limbs": n}``.
    """

    positions: VaultTreePositions
    points: np.ndarray
    legend: dict[str, str]
    title: str
    counts: dict[str, int] = field(default_factory=dict)


def leaf_colors(
    kg: VaultKG, note_ids: list[str], positions: VaultTreePositions, *, color_by: str
) -> tuple[np.ndarray, list[str], dict[str, str]]:
    """Per-leaf palette codes, the palette, and a legend.

    :param kg: An open vault graph.
    :param note_ids: Leaf order; matches the positions array.
    :param positions: The placement, for each note's group.
    :param color_by: ``"group"`` (top-level folder or tag), ``"tag"`` (first
        tag) or ``"links"`` (backlink count).
    :return: ``(codes, palette, legend)``; codes index into palette.
    :raises ValueError: On an unknown ``color_by``.
    """
    if color_by not in COLOR_BY:
        raise ValueError(f"color_by must be one of {', '.join(COLOR_BY)}, got {color_by!r}")
    if color_by == "links":
        health = vault_health(kg.store.con)
        palette = [c for _, c in LINK_BUCKETS]
        codes = [link_bucket(len(health.in_links.get(n, ()))) for n in note_ids]
        bounds = [u for u, _ in LINK_BUCKETS]
        labels = ["0 backlinks", "1", "2-3", "4-7", f"{bounds[-2] + 1}+"]
        return np.asarray(codes, dtype=float), palette, dict(zip(labels, palette, strict=True))

    if color_by == "group":
        keys = {n: positions.note_group.get(n, "").split("/")[0] or ROOT_LABEL for n in note_ids}
    else:
        tag_of: dict[str, str] = {}
        for n in note_ids:
            node = kg.store.node(n) or {}
            tag_of[n] = str(((node.get("metadata") or {}).get("tags") or [""])[0])
        keys = tag_of
    ranked = [k for k, _ in Counter(v for v in keys.values() if v).most_common()]
    colors = category_colors(ranked)
    palette = sorted(set(colors.values()) | {OTHER_COLOR})
    index = {c: i for i, c in enumerate(palette)}
    codes = [index[colors.get(keys[n], OTHER_COLOR)] for n in note_ids]
    legend = {k: c for k, c in colors.items() if c != OTHER_COLOR}
    if any(colors.get(keys[n], OTHER_COLOR) == OTHER_COLOR for n in note_ids):
        legend["other"] = OTHER_COLOR
    return np.asarray(codes, dtype=float), palette, legend


def leaf_scales(kg: VaultKG, note_ids: list[str], *, size_by: str) -> np.ndarray:
    """Per-leaf size multipliers.

    :param kg: An open vault graph.
    :param note_ids: Leaf order; matches the positions array.
    :param size_by: ``"links"`` (backlink count) or ``"none"`` (all 1.0).
    :return: ``(M,)`` multipliers of ``leaf_size``.
    :raises ValueError: On an unknown ``size_by``.
    """
    if size_by not in SIZE_BY:
        raise ValueError(f"size_by must be one of {', '.join(SIZE_BY)}, got {size_by!r}")
    if size_by == "none":
        return np.ones(len(note_ids))
    back = vault_health(kg.store.con).in_links
    counts = np.array([len(back.get(n, ())) for n in note_ids], dtype=float)
    return np.minimum(LEAF_SCALE_BASE + LEAF_SCALE_STEP * np.sqrt(counts), LEAF_SCALE_MAX)


def _line_mesh(segments: list[tuple[np.ndarray, np.ndarray]]) -> pv.PolyData:
    """One line mesh from ``(start, end)`` pairs: one draw call for all twigs."""
    import pyvista as pv  # noqa: PLC0415 -- the viz3d import boundary

    mesh = pv.PolyData()
    if not segments:
        return mesh
    n = len(segments)
    points = np.empty((n * 2, 3), dtype=float)
    points[0::2] = [s[0] for s in segments]
    points[1::2] = [s[1] for s in segments]
    cells = np.empty(n * 3, dtype=np.intp)
    cells[0::3] = 2
    cells[1::3] = np.arange(0, n * 2, 2)
    cells[2::3] = np.arange(1, n * 2 + 1, 2)
    mesh.points = points
    mesh.lines = cells
    return mesh


def build_vault_tree_scene(
    kg: VaultKG,
    plotter: pv.Plotter,
    *,
    group_by: str = "auto",
    color_by: str = "group",
    size_by: str = "links",
    tip_radius: float = 0.06,
    leaf_size: float = 0.35,
    organic: bool = True,
) -> VaultTree:
    """Grow the vault into *plotter* as one tree.

    :param kg: An open vault graph.
    :param plotter: PyVista plotter to compose into; its actors are cleared.
    :param group_by: ``"auto"``, ``"folder"`` or ``"tag"``; see
        :func:`vault_tree_positions`.
    :param color_by: ``"group"``, ``"tag"`` or ``"links"``; see :func:`leaf_colors`.
    :param size_by: ``"links"`` sizes each leaf by its backlinks, ``"none"``
        draws them all at ``leaf_size``; see :func:`leaf_scales`.
    :param tip_radius: Twig radius (organic) or trunk radius base (schematic).
    :param leaf_size: Leaf glyph radius before size scaling.
    :param organic: ``True`` grows wood by space colonization; ``False``
        draws the placement directly as a straight-line schematic, which is
        fast at any size and shows the layout the organic tree grows toward.
    :return: The composed :class:`VaultTree`.
    :raises ValueError: If the vault has no notes, or an option is unknown.
    """
    import pyvista as pv  # noqa: PLC0415 -- the viz3d import boundary
    from matplotlib.colors import ListedColormap  # noqa: PLC0415 -- arrives with pyvista

    notes = kg.store.query_nodes(kinds=["note"])
    positions = vault_tree_positions(notes, group_by=group_by)
    note_ids = list(positions.note_positions)
    leaf_points = np.array([positions.note_positions[n] for n in note_ids])
    codes, palette, legend = leaf_colors(kg, note_ids, positions, color_by=color_by)
    scales = leaf_scales(kg, note_ids, size_by=size_by)
    cmap = ListedColormap(palette)
    clim = [-0.5, len(palette) - 0.5]
    tip_radius *= positions.size_scale
    leaf_size *= positions.size_scale
    key = f"vault:{kg.repo_root.name}"

    plotter.clear_actors()
    plotter.enable_anti_aliasing("msaa")

    if organic:
        from kg_utils.viz3d import leaf_glyphs, tree_mesh  # noqa: PLC0415

        attractors = np.vstack([positions.trunk_guides, leaf_points])
        skeleton = grow_tree(attractors, np.zeros(3), key=key, tip_radius=tip_radius)
        wood = tree_mesh(skeleton)
        if wood.n_points:
            plotter.add_mesh(wood, color=WOOD_COLOR, smooth_shading=True, name="wood")
        leaves = leaf_glyphs(
            leaf_points,
            skeleton,
            size=leaf_size * scales,
            tint=codes,
            seed=seed_from_key(key + ":leaves"),
        )
        if leaves.n_points:
            plotter.add_mesh(
                leaves, scalars="tint", cmap=cmap, clim=clim, show_scalar_bar=False, name="leaves"
            )
        points = skeleton.points
    else:
        trunk = pv.Cylinder(
            center=(0.0, 0.0, positions.trunk_height / 2.0),
            direction=(0.0, 0.0, 1.0),
            radius=max(tip_radius * 4.0, 0.02),
            height=positions.trunk_height,
            resolution=12,
        )
        plotter.add_mesh(trunk, color=WOOD_COLOR, smooth_shading=True, name="wood")
        segments: list[tuple[np.ndarray, np.ndarray]] = []
        for g, tip in positions.limb_tips.items():
            parent = positions.limb_parent[g]
            start = positions.limb_tips[parent] if parent else np.array([0.0, 0.0, tip[2]])
            segments.append((start, tip))
        for n in note_ids:
            g = positions.note_group.get(n, "")
            anchor = positions.limb_tips[g] if g else np.zeros(3)
            segments.append((anchor, positions.note_positions[n]))
        twigs = _line_mesh(segments)
        if twigs.n_points:
            # A tube in world units: a pixel line width vanishes on zoom-out.
            tubes = twigs.tube(radius=max(tip_radius * 0.6, 0.01), n_sides=8)
            plotter.add_mesh(tubes, color=TWIG_COLOR, smooth_shading=True, name="branches")
        cloud = pv.PolyData(leaf_points)
        cloud.point_data["tint"] = codes
        cloud.point_data["leaf_scale"] = scales
        sphere = pv.Sphere(radius=leaf_size, theta_resolution=16, phi_resolution=16)
        plotter.add_mesh(
            cloud.glyph(geom=sphere, orient=False, scale="leaf_scale", factor=1.0),
            scalars="tint",
            cmap=cmap,
            clim=clim,
            show_scalar_bar=False,
            smooth_shading=True,
            name="leaves",
        )
        tips = np.array(list(positions.limb_tips.values())) if positions.limb_tips else None
        points = np.vstack([leaf_points, tips]) if tips is not None else leaf_points

    mode = "organic" if organic else "schematic"
    title = (
        f"{kg.repo_root.name} ({mode}, by {positions.group_by}) | "
        f"notes={len(note_ids)}  limbs={len(positions.limb_tips)}"
    )
    return VaultTree(
        positions=positions,
        points=points,
        legend=legend,
        title=title,
        counts={"notes": len(note_ids), "limbs": len(positions.limb_tips)},
    )


__all__ = [
    "VaultTree",
    "VaultTreePositions",
    "build_vault_tree_scene",
    "leaf_colors",
    "leaf_scales",
    "vault_tree_positions",
]
