"""snapshots.py -- vault graph snapshots on the shared ``kg_utils`` manager.

Follows the fleet snapshot standard: sets ``package_name``, adds vault
health figures through ``_domain_metrics``, and overrides nothing else.
Snapshots live in ``<vault>/.vaultkg/snapshots/``.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Any

from kg_utils.snapshots import Snapshot as Snapshot  # noqa: F401 -- re-export
from kg_utils.snapshots import SnapshotManager as _BaseSnapshotManager

from vaultkg.analysis import vault_health

__all__ = ["Snapshot", "SnapshotManager"]


class SnapshotManager(_BaseSnapshotManager):
    """VaultKG snapshot manager: adds orphans, wanted pages, components..."""

    package_name = "vault-kg"

    #: ``GraphStore.stats()`` counts the snapshots on disk, so saving one
    #: changes it; left in, dedup would never see two saves as unchanged.
    metrics_ignore = frozenset({"snapshot_count", "db_path"})
    dict_metric_deltas = ("node_counts", "edge_counts", "typed_links")

    def _domain_metrics(self, stats: dict[str, Any]) -> dict[str, Any]:
        """Vault health figures from the graph database.

        :param stats: Graph stats passed to ``capture()``; not used.
        :return: :meth:`~vaultkg.analysis.VaultHealth.metrics`.
        """
        if self.db_path is None or not self.db_path.exists():
            return {}
        with closing(sqlite3.connect(self.db_path)) as con:
            return vault_health(con).metrics()
