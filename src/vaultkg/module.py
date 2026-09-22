"""module.py -- VaultKG, the KGModule for Obsidian-style Markdown vaults."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kg_utils.extractor import KGExtractor
from kg_utils.pipeline import KGModule
from kg_utils.specs import QueryResult, SnippetPack
from kg_utils.store import GraphStore

from vaultkg import __version__
from vaultkg.analysis import VaultHealth, render_report, vault_health
from vaultkg.extractor import STRUCTURAL_RELS, VaultExtractor

_KIND_PRIORITY = {"note": 0, "heading": 1, "tag": 2, "attachment": 3}

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

    def health(self) -> VaultHealth:
        """Graph-health figures (hubs, orphans, bridges, wanted pages...)."""
        return vault_health(self.store.con)

    def analyze(self) -> str:
        """Markdown graph-health report. Never raises."""
        try:
            return render_report(self.health(), self.stats())
        except Exception as exc:  # noqa: BLE001 -- contract: never raise
            return f"# VaultKG Analysis\n\nAnalysis failed: {exc}\n"
