"""VaultKG MCP server: an Obsidian-style vault graph as Model Context Protocol tools.

Built on the fleet's shared server base, :mod:`kg_utils.mcp`. The server
answers the fleet's canonical tools -- ``stats``, ``query``, ``pack``,
``get_node``, ``neighbors`` -- under the same names as every other KG server,
then VaultKG's own: ``note_links``, ``analyze_vault`` and the three snapshot
tools. ``get_node`` and ``neighbors`` take a note's vault path as well as its id.

The tool list is not kept by hand anywhere: each tool's docstring is its
description, the server's instructions are generated from them, and::

    vaultkg mcp --manifest

prints the whole list as JSON without opening the graph.

Hardening follows FLEET_STANDARDS. ``query()``/``pack()`` arguments are
validated by the ``KGModule`` base; node ids and link limits by ``VaultKG``
itself, which the CLI shares. Out-of-range values are rejected, never clamped.
The graph is opened when a session starts and closed when it ends, and a vault
with no graph is refused rather than served empty.

Usage
-----
::

    vaultkg mcp --repo ~/brain

``vaultkg-mcp`` is the same command under its older name, and also takes
``--vault`` for ``--repo``, so configs written for it keep working.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from kg_utils.mcp import Context, KGServer, kg_from, make_server
from kg_utils.validation import bounded_int

from vaultkg import __version__
from vaultkg.module import MAX_LIMIT, VaultKG
from vaultkg.snapshots import SnapshotManager

PREAMBLE = (
    "VaultKG is a knowledge graph of one Obsidian-style Markdown vault. Every "
    "edge is a link the author wrote: [[wikilinks]], Markdown links, embeds, tags, "
    "and typed links such as 'supports:: [[X]]' or frontmatter keys holding "
    "wikilinks, which become relations like SUPPORTS or CONTRADICTS. Nothing is "
    "extracted by a model. Node ids look like 'note:wiki/Retrieval.md', "
    "'heading:wiki/Retrieval.md#failure-modes', 'tag:ml/retrieval', "
    "'attachment:assets/diagram.png', and 'missing:<target>' for a link target no "
    "note answers to.\n\n"
    "## Workflows\n\n"
    "- Orient: stats, then analyze_vault for hubs, orphans and wanted pages.\n"
    "- Find notes on a topic: query, or pack for their text.\n"
    "- Backlinks: note_links('wiki/Retrieval.md', direction='in').\n"
    "- A note's typed claims: note_links(id, rel='SUPPORTS') or rel='CONTRADICTS'.\n"
    "- One node's metadata (title, tags, aliases, dates): get_node.\n\n"
    "A note may be named by its id or by its vault path, with or without '.md'. "
    "query and pack need a build with the vector index; without one they return "
    "an error saying so.\n\n"
    "## Argument bounds\n\n"
    "Out-of-range arguments are rejected with a message naming the range, never "
    "clamped. k 1-100, hop 0-5, max_nodes 1-500, limit 1-500, queries at most 2000 "
    "characters, node ids at most 500."
)


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


def _snapshot_mgr(ctx: Context) -> SnapshotManager:
    """The served vault's snapshot manager."""
    kg: VaultKG = kg_from(ctx)
    return SnapshotManager(kg.repo_root / VaultKG._default_dir / "snapshots", db_path=kg.db_path)


def note_links(
    node_id: str, ctx: Context, direction: str = "out", rel: str = "", limit: int = 50
) -> str:
    """Links at a node: what it links to, or with direction="in", its backlinks.

    :param node_id: Node id, or a note's vault path.
    :param direction: ``"out"`` (the node links to them) or ``"in"`` (they link to it).
    :param rel: One relation (LINKS_TO, EMBEDS, TAGGED, CONTAINS, or a typed one
        such as SUPPORTS), or ``""`` for all.
    :param limit: Links returned, 1-500.
    :return: JSON list of {rel, node, kind, name, evidence, via}. evidence
        carries the source line numbers and link aliases; via is the node the
        link lands on, which for a note's backlinks may be one of its sections.
    """
    return _json(kg_from(ctx).links(node_id, direction=direction, rel=rel, limit=limit))


def analyze_vault(ctx: Context) -> str:
    """Graph-health report: hubs, bridges, wanted pages, orphans, islands, typed links.

    :return: Markdown report.
    """
    return kg_from(ctx).analyze()


def snapshot_list(ctx: Context, limit: int = 10) -> str:
    """Saved metric snapshots, newest first.

    :param limit: Snapshots returned, 1-500.
    :return: JSON list of manifest entries.
    """
    limit = bounded_int("limit", limit, 1, MAX_LIMIT)
    return _json(_snapshot_mgr(ctx).list_snapshots(limit=limit))


def snapshot_show(ctx: Context, key: str = "latest") -> str:
    """One snapshot in full.

    :param key: Snapshot key (a release tag or UTC timestamp), or ``"latest"``.
    :return: JSON snapshot, or ``null`` if there is none.
    """
    snap = _snapshot_mgr(ctx).load_snapshot(_snapshot_key(key))
    return _json(snap.to_dict() if snap else None)


def snapshot_diff(key_a: str, key_b: str, ctx: Context) -> str:
    """Compare two snapshots (B minus A).

    :param key_a: Earlier snapshot key.
    :param key_b: Later snapshot key.
    :return: JSON with both snapshots' metrics and the deltas.
    """
    result = _snapshot_mgr(ctx).diff_snapshots(_snapshot_key(key_a), _snapshot_key(key_b))
    if "error" in result:
        raise ValueError(result["error"])
    return _json(result)


#: Domain tools, registered after the canonical five in this order.
EXTRA_TOOLS = (note_links, analyze_vault, snapshot_list, snapshot_show, snapshot_diff)


def build_server(
    repo: str | Path,
    db: str | Path | None = None,
    vectors: str | Path | None = None,
    model: str | None = None,
) -> KGServer:
    """Build the VaultKG MCP server for one vault, without opening its graph.

    :param repo: Vault root.
    :param db: Graph database; ``None`` for ``<repo>/.vaultkg/graph.sqlite``.
    :param vectors: Vector store; ``None`` for ``<repo>/.vaultkg/vectors.sqlite``.
    :param model: Embedding model; ``None`` for the KGModule default.
    :return: The server; serve it with :func:`kg_utils.mcp.run`.
    """
    root = Path(repo).resolve()
    kwargs: dict[str, Any] = {"model": model} if model else {}

    def open_kg() -> VaultKG:
        return VaultKG(root, db, vectors, **kwargs)

    server = make_server(
        open_kg, name="vaultkg", kind="vault", version=__version__, instructions=PREAMBLE
    )
    for fn in EXTRA_TOOLS:
        server.tool()(fn)
    return server


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``vaultkg-mcp``: the same command as ``vaultkg mcp``.

    ``--vault`` is taken as ``--repo``, the spelling ``vaultkg-mcp`` used
    before the standard command.

    :param argv: Arguments; ``None`` for ``sys.argv[1:]``.
    """
    from vaultkg.cli import mcp_command  # noqa: PLC0415 -- cli imports this module lazily

    args = sys.argv[1:] if argv is None else argv
    args = ["--repo" if a == "--vault" else a for a in args]
    mcp_command.main(args=args, prog_name="vaultkg-mcp")


if __name__ == "__main__":
    main()
