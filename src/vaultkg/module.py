"""module.py -- VaultKG, the KGModule for Obsidian-style Markdown vaults."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kg_utils.extractor import KGExtractor
from kg_utils.pipeline import KGModule
from kg_utils.specs import QueryResult, SnippetPack
from kg_utils.store import GraphStore
from kg_utils.validation import bounded_int

from vaultkg import __version__
from vaultkg.analysis import VaultHealth, render_report, vault_health
from vaultkg.extractor import STRUCTURAL_RELS, VaultExtractor

_KIND_PRIORITY = {"note": 0, "heading": 1, "tag": 2, "attachment": 3}

#: Node id prefixes the extractor writes (``missing:`` is an unresolved target).
_ID_PREFIXES = ("note:", "heading:", "tag:", "attachment:", "missing:")
#: Upper bound on :meth:`VaultKG.links` results and on node id length.
MAX_LIMIT = 500
MAX_ID_LEN = 500

#: What the SDK's generic ``GraphStore.stats()`` computes for a code graph. A
#: vault has no modules or functions, so these are dropped rather than
#: reported as zero.
_CODE_GRAPH_KEYS = frozenset(
    {"module_count", "class_count", "function_count", "method_count", "docstring_coverage"}
)


class VaultKG(KGModule):
    """Knowledge graph over one Markdown vault.

    Artefacts live in ``<vault>/.vaultkg/``; Obsidian ignores dot-folders, so
    they never show up as notes.

    :param repo_root: Vault root.
    :param exclude: Directory names or glob patterns to skip when building,
        on top of every dot-directory and ``node_modules``.
    :param kwargs: Passed to :class:`kg_utils.pipeline.KGModule`
        (``db_path``, ``vectors_path``, ``model``...).
    """

    _default_dir = ".vaultkg"

    def __init__(
        self,
        repo_root: str | Path,
        db_path: str | Path | None = None,
        vectors_path: str | Path | None = None,
        *,
        exclude: list[str] | tuple[str, ...] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(repo_root, db_path, vectors_path, **kwargs)
        self.exclude = tuple(exclude or ())

    # ------------------------------------------------------------ contract
    def kind(self) -> str:
        return "vault"

    def make_extractor(self) -> KGExtractor:
        return VaultExtractor(self.repo_root, {"exclude": list(self.exclude)})

    def _post_build_hook(self, store: GraphStore) -> None:
        """Stamp the builder version KGRAG reads (``docs/KG_BUILDER_VERSION_SPEC.md``)."""
        con = store.con
        con.execute(
            "CREATE TABLE IF NOT EXISTS _kgrag_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        con.executemany(
            "INSERT OR REPLACE INTO _kgrag_meta (key, value) VALUES (?, ?)",
            [
                ("builder_name", "vault_kg"),
                ("builder_version", __version__),
                ("built_at", datetime.now(UTC).isoformat()),
            ],
        )
        con.commit()

    def _kind_priority(self, kind: str) -> int:
        return _KIND_PRIORITY.get(kind, 99)

    def relations(self) -> tuple[str, ...]:
        """Every relation in the built graph, structural ones first.

        Typed links are whatever keys a vault uses (``SUPPORTS``, ``UP``...),
        so query expansion follows the relations actually present rather than
        a fixed list.
        """
        present = {r[0] for r in self.store.con.execute("SELECT DISTINCT rel FROM edges")}
        return tuple(r for r in STRUCTURAL_RELS if r in present) + tuple(
            sorted(present - set(STRUCTURAL_RELS))
        )

    def query(
        self, q: str, *, k: int = 8, hop: int = 1, rels: tuple[str, ...] | None = None, **kw: Any
    ) -> QueryResult:
        """Semantic seeding plus link expansion.

        :param q: Natural-language query.
        :param k: Seed hits.
        :param hop: Expansion hops along links, embeds, tags and headings.
        :param rels: Relations to expand along; default every relation present.
        :return: Ranked nodes and the edges among them.
        """
        return super().query(q, k=k, hop=hop, rels=rels or self.relations(), **kw)

    def pack(
        self, q: str, *, k: int = 8, hop: int = 1, rels: tuple[str, ...] | None = None, **kw: Any
    ) -> SnippetPack:
        """Like :meth:`query`, with each note or section's source text attached.

        :param q: Natural-language query.
        :param k: Seed hits.
        :param hop: Expansion hops.
        :param rels: Relations to expand along; default every relation present.
        :return: The pack.
        """
        return super().pack(q, k=k, hop=hop, rels=rels or self.relations(), **kw)

    # ------------------------------------------------------------ reporting
    def stats(self) -> dict[str, Any]:
        """Store counts, plus note/link figures a vault owner cares about.

        :return: ``total_nodes``, ``total_edges``, ``node_counts``,
            ``edge_counts``, ``meaningful_nodes`` (everything but unresolved
            targets), plus ``notes``, ``headings``, ``tags``, ``unresolved``.
        """
        s = {k: v for k, v in super().stats().items() if k not in _CODE_GRAPH_KEYS}
        nc = s.get("node_counts", {})
        s["notes"] = nc.get("note", 0)
        s["headings"] = nc.get("heading", 0)
        s["tags"] = nc.get("tag", 0)
        s["unresolved"] = nc.get("symbol", 0)
        return s

    # ------------------------------------------------------------ lookup
    def node(self, node_id: str) -> dict[str, Any] | None:
        """One node, by id or by the note's vault path.

        :param node_id: ``note:wiki/X.md``, ``heading:...``, ``tag:...``, or a
            bare vault path such as ``wiki/X.md`` or ``wiki/X``.
        :return: The node, or ``None`` if there is none.
        :raises ValueError: On an empty or over-long id.
        """
        return self.store.node(normalize_node_id(node_id))

    def links(
        self, node_id: str, *, direction: str = "out", rel: str = "", limit: int = 50
    ) -> list[dict[str, Any]]:
        """Links at a node: what it links to, or what links to it (backlinks).

        :param node_id: Node id or vault path, as for :meth:`node`.
        :param direction: ``"out"`` (the node is the source) or ``"in"``.
        :param rel: One relation (``LINKS_TO``, ``SUPPORTS``...), or ``""`` for all.
        :param limit: Links returned, 1-500.
        :return: ``{rel, node, kind, name, evidence}`` per link, ordered by
            relation then node id.
        :raises ValueError: On a bad id, direction or limit.
        """
        nid = normalize_node_id(node_id)
        if direction not in ("out", "in"):
            raise ValueError(f"direction must be 'out' or 'in', got {direction!r}")
        bounded_int("limit", limit, 1, MAX_LIMIT)
        near, far = ("src", "dst") if direction == "out" else ("dst", "src")
        sql = (
            f"SELECT e.rel, e.{far}, n.kind, n.name, e.evidence FROM edges e "
            f"LEFT JOIN nodes n ON n.id = e.{far} WHERE e.{near} = ?"
        )
        params: list[Any] = [nid]
        if rel:
            sql += " AND e.rel = ?"
            params.append(rel.strip().upper())
        sql += f" ORDER BY e.rel, e.{far} LIMIT ?"
        params.append(limit)
        return [
            {
                "rel": r[0],
                "node": r[1],
                "kind": r[2],
                "name": r[3],
                "evidence": json.loads(r[4]) if r[4] else {},
            }
            for r in self.store.con.execute(sql, params)
        ]

    def health(self) -> VaultHealth:
        """Graph-health figures (hubs, orphans, bridges, wanted pages...)."""
        return vault_health(self.store.con)

    def analyze(self) -> str:
        """Markdown graph-health report. Never raises."""
        try:
            return render_report(self.health(), self.stats())
        except Exception as exc:  # noqa: BLE001 -- contract: never raise
            return f"# VaultKG Analysis\n\nAnalysis failed: {exc}\n"


def normalize_node_id(raw: str) -> str:
    """Normalise a node id supplied from outside (a CLI argument, an MCP call).

    Agents echo ids back with backticks or quotes, and people type a note's
    path rather than its id, so ``wiki/X``, ``wiki/X.md`` and ``note:wiki/X.md``
    all name the same note.

    :param raw: The id as given.
    :return: A node id with one of the extractor's prefixes.
    :raises ValueError: If empty after stripping, or longer than 500 characters.
    """
    nid = raw.strip().strip("`'\"").strip()
    if not nid:
        raise ValueError("node_id must not be empty")
    if len(nid) > MAX_ID_LEN:
        raise ValueError(f"node_id must be at most {MAX_ID_LEN} characters, got {len(nid)}")
    if nid.startswith(_ID_PREFIXES):
        return nid
    path = nid.lstrip("/")
    return "note:" + (path if path.lower().endswith(".md") else path + ".md")
