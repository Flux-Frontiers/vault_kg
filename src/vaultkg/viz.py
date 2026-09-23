"""viz.py -- the vault's link graph as a self-contained interactive HTML page.

The renderer is ``kg_utils.viz.build_graph_html``, shared with every other KG
module. What lives here is only what is about a vault: which kinds exist, how
relations are coloured, what a tooltip shows, and how notes are chosen when
the whole vault is too big to draw.

Notes are sized by backlinks (distinct notes linking in), so hubs stand out
without reading labels. pyvis arrives with the ``viz`` extra and is imported
by the SDK inside the render call; the CLI imports this module inside its
command, so a bare install never pulls it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any, Final

from kg_utils.analysis import ScoreSet
from kg_utils.viz import GraphTheme, KindStyle, TooltipRow, TooltipSpec, build_graph_html

from vaultkg.analysis import vault_health
from vaultkg.module import VaultKG, normalize_node_id
from vaultkg.theme import (
    KIND_COLOR,
    REL_COLOR,
    TYPED_REL_COLOR,
    category_colors,
    top_folder,
)

#: vis.js shape per kind, so the view reads without colour.
KIND_SHAPE: Final[dict[str, str]] = {
    "note": "dot",
    "heading": "dot",
    "tag": "diamond",
    "attachment": "square",
    "symbol": "triangleDown",
}
KIND_SIZE: Final[dict[str, int]] = {
    "note": 16,
    "heading": 8,
    "tag": 12,
    "attachment": 10,
    "symbol": 9,
}

#: Kinds drawn by default. Headings are opt-in: a vault has several per note,
#: and they bury the note-to-note links the view exists to show.
DEFAULT_KINDS: Final[tuple[str, ...]] = ("note", "tag", "attachment", "symbol")
ALL_KINDS: Final[tuple[str, ...]] = ("note", "heading", "tag", "attachment", "symbol")


def _kind_row(node: Mapping[str, Any]) -> str:
    """Tooltip row: the kind, with ``symbol`` shown as what it means."""
    kind = str(node.get("kind", ""))
    return "missing note" if kind == "symbol" else kind


def _tags_row(node: Mapping[str, Any]) -> str:
    """Tooltip row: a note's tags, ``#a #b``."""
    tags = (node.get("metadata") or {}).get("tags") or []
    return " ".join(f"#{t}" for t in tags)


VAULT_TOOLTIP: Final[TooltipSpec] = TooltipSpec(
    title="name",
    rows=(
        TooltipRow(_kind_row),
        TooltipRow("module_path"),
        TooltipRow(_tags_row),
    ),
    body="docstring",
)


def vault_theme(relations: list[str], folders: list[str] | None = None) -> GraphTheme:
    """The visual vocabulary for a vault.

    :param relations: Relations present in the graph; typed ones not in
        :data:`~vaultkg.theme.REL_COLOR` get the shared typed-link colour.
    :param folders: Top-level folders, most notes first. Notes are coloured
        by folder, matching the 3-D tree; ``None`` colours every note alike.
    :return: A :class:`~kg_utils.viz.GraphTheme`.
    """
    kinds = {
        k: KindStyle(color=KIND_COLOR[k], shape=KIND_SHAPE[k], size=KIND_SIZE[k])
        for k in KIND_COLOR
    }
    for folder, color in category_colors(folders or []).items():
        kinds[f"note:{folder}"] = KindStyle(
            color=color, shape=KIND_SHAPE["note"], size=KIND_SIZE["note"]
        )

    def resolve(node: Mapping[str, Any]) -> str:
        kind = str(node.get("kind", ""))
        if kind != "note" or not folders:
            return kind
        return f"note:{top_folder(str(node.get('module_path') or ''))}"

    rels = {r: REL_COLOR.get(r, TYPED_REL_COLOR) for r in relations}
    return GraphTheme(
        kinds=kinds,
        fallback=KindStyle(color="#8C8C8C", shape="dot", size=10),
        relations=rels,
        relation_fallback=TYPED_REL_COLOR,
        resolve_kind=resolve,
    )


def backlink_scores(kg: VaultKG) -> ScoreSet:
    """Distinct notes linking in, per note, as a score set for node sizing.

    :param kg: An open vault graph.
    :return: A ``ScoreSet`` over every note; rank 1 is the most linked.
    """
    health = vault_health(kg.store.con)
    scores = {n: float(len(health.in_links.get(n, ()))) for n in health.notes}
    ordered = sorted(scores, key=lambda n: (-scores[n], n))
    ranks = {n: i + 1 for i, n in enumerate(ordered)}
    return ScoreSet(metric="backlinks", table="vault", scores=scores, ranks=ranks)


def _degree(kg: VaultKG) -> dict[str, int]:
    """Edges touching each node, in either direction."""
    rows = kg.store.con.execute(
        "SELECT id, COUNT(*) FROM (SELECT src AS id FROM edges UNION ALL "
        "SELECT dst AS id FROM edges) GROUP BY id"
    )
    return {r[0]: r[1] for r in rows}


def link_graph_html(
    kg: VaultKG,
    *,
    root: str | None = None,
    hops: int = 1,
    max_nodes: int = 200,
    kinds: tuple[str, ...] = DEFAULT_KINDS,
    height: str = "800px",
) -> tuple[str, int, int]:
    """Render the vault's link graph as a self-contained HTML page.

    With ``root``, the picture is that note's neighbourhood, ``hops`` links
    out in either direction. Without one it is the most connected part of the
    vault: nodes ranked by how many edges touch them, cut at ``max_nodes``.

    :param kg: An open vault graph.
    :param root: A node id or a note's vault path to centre on, or ``None``.
    :param hops: Links to expand from ``root``.
    :param max_nodes: Node budget.
    :param kinds: Node kinds to draw; the root is drawn whatever its kind.
    :param height: CSS height of the canvas.
    :return: ``(html, nodes drawn, edges drawn)``.
    :raises ValueError: If ``root`` is not in the graph, a kind is unknown, or
        nothing is left to draw.
    """
    unknown = set(kinds) - set(ALL_KINDS)
    if unknown:
        raise ValueError(f"unknown kind(s): {', '.join(sorted(unknown))}")
    store = kg.store
    root_id = normalize_node_id(root) if root is not None else None
    degree = _degree(kg)

    if root_id is not None:
        if store.node(root_id) is None:
            raise ValueError(f"no such node: {root_id}")
        reach = store.expand({root_id}, hop=hops, rels=kg.relations())
        # Nearest first, then the most connected, so a budget cut keeps the
        # neighbourhood's core.
        ids = sorted(reach, key=lambda i: (reach[i].best_hop, -degree.get(i, 0), i))
        nodes = [n for n in (store.node(i) for i in ids) if n is not None]
        nodes = [n for n in nodes if n["id"] == root_id or n["kind"] in kinds]
    else:
        nodes = store.query_nodes(kinds=list(kinds))
        nodes.sort(key=lambda n: (-degree.get(n["id"], 0), n["id"]))

    if not nodes:
        raise ValueError("nothing to draw")
    nodes = nodes[:max_nodes]
    edges = store.edges_within({n["id"] for n in nodes})

    counts = Counter(
        top_folder(str(n.get("module_path") or "")) for n in nodes if n["kind"] == "note"
    )
    folders = [f for f, _ in counts.most_common()]
    html = build_graph_html(
        nodes,
        edges,
        theme=vault_theme(list(kg.relations()), folders),
        tooltip=VAULT_TOOLTIP,
        scores=backlink_scores(kg),
        height=height,
        highlight_ids={root_id} if root_id else None,
    )
    return html, len(nodes), len(edges)


__all__ = ["VAULT_TOOLTIP", "backlink_scores", "link_graph_html", "vault_theme"]
