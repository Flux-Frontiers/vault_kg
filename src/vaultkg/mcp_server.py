"""VaultKG MCP server: an Obsidian-style vault graph as Model Context Protocol tools.

Tools
-----
graph_stats()
    Note, heading, tag and link counts. Start here.
query_vault(q, k, hop)
    Semantic search over notes and sections, then along their links.
pack_vault(q, k, hop, max_nodes)
    The same search with each note or section's text, as Markdown.
get_node(node_id)
    One note, heading, tag or attachment with its metadata.
note_links(node_id, direction, rel, limit)
    What a note links to, or what links to it (backlinks).
analyze_vault()
    Graph-health report: hubs, bridges, wanted pages, orphans, islands.
snapshot_list(limit), snapshot_show(key), snapshot_diff(key_a, key_b)
    Saved metric snapshots.

Hardening follows FLEET_STANDARDS. ``query()``/``pack()`` arguments are
validated by the ``KGModule`` base (kgmodule-utils 0.23.0); node ids and link
limits by ``VaultKG`` itself, which the CLI shares. Out-of-range values are
rejected, never clamped. A ``lifespan`` hook closes the graph when the server
stops, on either transport.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from kg_utils.validation import bounded_int
from mcp.server.fastmcp import FastMCP

from vaultkg.module import MAX_LIMIT, VaultKG
from vaultkg.snapshots import SnapshotManager

_kg: VaultKG | None = None
_snapshot_mgr: SnapshotManager | None = None


def _get_kg() -> VaultKG:
    if _kg is None:
        raise RuntimeError("VaultKG not initialised. Run the server via 'vaultkg-mcp --vault PATH'")
    return _kg


def _get_snapshot_mgr() -> SnapshotManager:
    if _snapshot_mgr is None:
        raise RuntimeError(
            "SnapshotManager not initialised. Run the server via 'vaultkg-mcp --vault PATH'"
        )
    return _snapshot_mgr


#: A snapshot key is a release tag or a UTC timestamp. It becomes a file name
#: under the snapshots directory, so path separators are refused outright.
_SNAPSHOT_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}")


def _snapshot_key(key: str) -> str:
    """Validate a snapshot key before it becomes a file name.

    :param key: Key as given by the caller.
    :return: The stripped key.
    :raises ValueError: If it is not a plain tag or timestamp.
    """
    k = key.strip()
    if not _SNAPSHOT_KEY.fullmatch(k):
        raise ValueError(f"invalid snapshot key {key!r}: expected a tag or timestamp")
    return k


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """Close the long-lived VaultKG when the server shuts down.

    Per FLEET_STANDARDS (resource cleanup, settled 2026-08-24). ``main()`` sets
    ``_kg`` before ``mcp.run()``, and the stdio and SSE transports both route
    through the same ``Server.run()``, so this one hook covers both.
    """
    try:
        yield
    finally:
        if _kg is not None:
            _kg.close()


mcp = FastMCP(
    "vaultkg",
    lifespan=_lifespan,
    instructions=(
        "VaultKG is a knowledge graph of one Obsidian-style Markdown vault. Every "
        "edge is a link the author wrote: [[wikilinks]], Markdown links, embeds, tags, "
        "and typed links such as 'supports:: [[X]]' or frontmatter keys holding "
        "wikilinks, which become relations like SUPPORTS or CONTRADICTS. Nothing is "
        "extracted by a model. Node ids look like 'note:wiki/Retrieval.md', "
        "'heading:wiki/Retrieval.md#failure-modes', 'tag:ml/retrieval', "
        "'attachment:assets/diagram.png', and 'missing:<target>' for a link target no "
        "note answers to.\n\n"
        "## Workflows\n\n"
        "- Orient: graph_stats, then analyze_vault for hubs, orphans and wanted pages.\n"
        "- Find notes on a topic: query_vault, or pack_vault for their text.\n"
        "- Backlinks: note_links('wiki/Retrieval.md', direction='in').\n"
        "- A note's typed claims: note_links(id, rel='SUPPORTS') or rel='CONTRADICTS'.\n"
        "- One node's metadata (title, tags, aliases, dates): get_node.\n\n"
        "A note may be named by its id or by its vault path, with or without '.md'. "
        "query_vault and pack_vault need a build with the vector index; without one "
        "they return an error saying so.\n\n"
        "## Argument bounds\n\n"
        "Out-of-range arguments are rejected with a message naming the range, never "
        "clamped. k 1-100, hop 0-5, max_nodes 1-500, limit 1-500, queries at most 2000 "
        "characters, node ids at most 500."
    ),
)


@mcp.tool()
def graph_stats() -> str:
    """What the vault graph holds: note, heading, tag and unresolved-link counts.

    :return: JSON with total_nodes, total_edges, node_counts, edge_counts,
        notes, headings, tags and unresolved.
    """
    s = _get_kg().stats()
    keys = (
        "total_nodes",
        "meaningful_nodes",
        "total_edges",
        "node_counts",
        "edge_counts",
        "notes",
        "headings",
        "tags",
        "unresolved",
    )
    return _json({k: s[k] for k in keys if k in s})


@mcp.tool()
def query_vault(q: str, k: int = 8, hop: int = 1) -> str:
    """Semantic search over notes and sections, then expansion along their links.

    :param q: Natural-language query.
    :param k: Seed hits, 1-100.
    :param hop: Link hops to expand, 0-5 (0 = semantic hits only).
    :return: JSON QueryResult: ranked nodes and the edges among them.
    """
    return _get_kg().query(q, k=k, hop=hop).to_json()


@mcp.tool()
def pack_vault(q: str, k: int = 8, hop: int = 1, max_nodes: int = 25) -> str:
    """Like query_vault, with each note or section's source text, as Markdown.

    :param q: Natural-language query.
    :param k: Seed hits, 1-100.
    :param hop: Link hops to expand, 0-5.
    :param max_nodes: Nodes in the pack, 1-500.
    :return: Markdown snippet pack with vault paths and line spans.
    """
    return _get_kg().pack(q, k=k, hop=hop, max_nodes=max_nodes).to_markdown()


@mcp.tool()
def get_node(node_id: str) -> str:
    """One node with its metadata.

    :param node_id: Node id, or a note's vault path (``wiki/Retrieval`` works).
    :return: JSON node, or ``null`` if there is no such node.
    """
    return _json(_get_kg().node(node_id))


@mcp.tool()
def note_links(node_id: str, direction: str = "out", rel: str = "", limit: int = 50) -> str:
    """Links at a node: what it links to, or with direction="in", its backlinks.

    :param node_id: Node id, or a note's vault path.
    :param direction: ``"out"`` (the node links to them) or ``"in"`` (they link to it).
    :param rel: One relation (LINKS_TO, EMBEDS, TAGGED, CONTAINS, or a typed one
        such as SUPPORTS), or ``""`` for all.
    :param limit: Links returned, 1-500.
    :return: JSON list of {rel, node, kind, name, evidence}; evidence carries
        the source line numbers and link aliases.
    """
    return _json(_get_kg().links(node_id, direction=direction, rel=rel, limit=limit))


@mcp.tool()
def analyze_vault() -> str:
    """Graph-health report: hubs, bridges, wanted pages, orphans, islands, typed links.

    :return: Markdown report.
    """
    return _get_kg().analyze()


@mcp.tool()
def snapshot_list(limit: int = 10) -> str:
    """Saved metric snapshots, newest first.

    :param limit: Snapshots returned, 1-500.
    :return: JSON list of manifest entries.
    """
    limit = bounded_int("limit", limit, 1, MAX_LIMIT)
    return _json(_get_snapshot_mgr().list_snapshots(limit=limit))


@mcp.tool()
def snapshot_show(key: str = "latest") -> str:
    """One snapshot in full.

    :param key: Snapshot key (a release tag or UTC timestamp), or ``"latest"``.
    :return: JSON snapshot, or ``null`` if there is none.
    """
    snap = _get_snapshot_mgr().load_snapshot(_snapshot_key(key))
    return _json(snap.to_dict() if snap else None)


@mcp.tool()
def snapshot_diff(key_a: str, key_b: str) -> str:
    """Compare two snapshots (B minus A).

    :param key_a: Earlier snapshot key.
    :param key_b: Later snapshot key.
    :return: JSON with both snapshots' metrics and the deltas.
    """
    result = _get_snapshot_mgr().diff_snapshots(_snapshot_key(key_a), _snapshot_key(key_b))
    if "error" in result:
        raise ValueError(result["error"])
    return _json(result)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="vaultkg-mcp",
        description="VaultKG MCP server: an Obsidian vault's link graph for AI agents.",
    )
    p.add_argument(
        "--vault",
        "--repo",
        dest="vault",
        default=".",
        help="Vault root (--repo is accepted for fleet configs).",
    )
    p.add_argument("--db", default=None, help="Graph path (default: <vault>/.vaultkg/graph.sqlite)")
    p.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Start the MCP server.

    :param argv: Argument vector; defaults to ``sys.argv[1:]``.
    """
    global _kg, _snapshot_mgr

    args = _parse_args(argv)
    vault = Path(args.vault).resolve()
    kg = VaultKG(vault, db_path=args.db)
    if not kg.db_path.exists():
        # Opening the store would create an empty graph, which every tool would
        # then report as a vault with no notes. Refuse, as the CLI does.
        raise SystemExit(f"vaultkg-mcp: no graph at {kg.db_path}; run `vaultkg build` first")
    _kg = kg
    _snapshot_mgr = SnapshotManager(vault / VaultKG._default_dir / "snapshots", db_path=_kg.db_path)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
