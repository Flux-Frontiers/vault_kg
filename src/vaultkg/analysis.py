"""analysis.py -- graph-health metrics for a built vault graph.

Every figure here is computed from the stored graph with plain graph
algorithms: degree counts, connected components and articulation points. No
model reads the notes, so a report on the same build is always the same
report.

The note graph used throughout collapses heading targets onto their note and
ignores ``CONTAINS`` and ``TAGGED``: two notes are linked when one links,
embeds or typed-links the other.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

#: Relations that are structure within a note or a label, not a note-to-note link.
NON_LINK_RELS = ("CONTAINS", "TAGGED")
PLAIN_LINK_RELS = ("LINKS_TO", "EMBEDS")


def note_of(node_id: str) -> str | None:
    """The ``note:`` id a link target belongs to, or ``None`` if it is not a note.

    :param node_id: ``note:...`` or ``heading:<path>#<slug>`` id.
    :return: The owning note id.
    """
    if node_id.startswith("note:"):
        return node_id
    if node_id.startswith("heading:"):
        return "note:" + node_id.removeprefix("heading:").rsplit("#", 1)[0]
    return None


@dataclass
class VaultHealth:
    """Graph-health figures for one vault.

    :param notes: Note ids.
    :param links: Directed note -> note pairs with their relations.
    :param in_links: Note id -> distinct notes linking to it.
    :param out_links: Note id -> distinct notes it links to.
    :param wanted: Missing target -> distinct notes linking to it.
    :param typed: Typed relation -> ``(src, dst)`` note pairs.
    :param tags: Tag id -> number of notes tagged.
    :param ambiguous: Links resolved among several same-named notes.
    :param frontmatter_errors: Note id -> YAML error.
    """

    notes: list[str]
    titles: dict[str, str]
    links: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    in_links: dict[str, set[str]] = field(default_factory=dict)
    out_links: dict[str, set[str]] = field(default_factory=dict)
    wanted: dict[str, set[str]] = field(default_factory=dict)
    typed: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    tags: Counter[str] = field(default_factory=Counter)
    ambiguous: int = 0
    frontmatter_errors: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------ derived
    def orphans(self) -> list[str]:
        """Notes with no link in or out."""
        return [n for n in self.notes if not self.in_links.get(n) and not self.out_links.get(n)]

    def dead_ends(self) -> list[str]:
        """Notes other notes link to that link to nothing themselves."""
        return [n for n in self.notes if self.in_links.get(n) and not self.out_links.get(n)]

    def hubs(self, top: int = 10) -> list[tuple[str, int]]:
        """Notes with the most distinct notes linking in."""
        ranked = sorted(self.in_links.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        return [(n, len(s)) for n, s in ranked[:top] if s]

    def _undirected(self) -> dict[str, set[str]]:
        adj: dict[str, set[str]] = defaultdict(set)
        for a, b in self.links:
            if a != b:
                adj[a].add(b)
                adj[b].add(a)
        return adj

    def components(self) -> list[list[str]]:
        """Connected components of linked notes, largest first (orphans excluded)."""
        adj = self._undirected()
        seen: set[str] = set()
        out: list[list[str]] = []
        for start in sorted(adj):
            if start in seen:
                continue
            comp, stack = [], [start]
            seen.add(start)
            while stack:
                v = stack.pop()
                comp.append(v)
                for w in adj[v]:
                    if w not in seen:
                        seen.add(w)
                        stack.append(w)
            out.append(sorted(comp))
        return sorted(out, key=lambda c: (-len(c), c[0]))

    def bridges(self) -> list[tuple[str, int]]:
        """Articulation notes: removing one splits its component. With degree.

        Iterative Tarjan, so a long chain of notes cannot hit the recursion
        limit.
        """
        adj = {k: sorted(v) for k, v in self._undirected().items()}
        disc: dict[str, int] = {}
        low: dict[str, int] = {}
        cut: set[str] = set()
        t = 0
        for root in sorted(adj):
            if root in disc:
                continue
            disc[root] = low[root] = t
            t += 1
            children = 0
            stack: list[tuple[str, str | None, int]] = [(root, None, 0)]
            while stack:
                v, parent, i = stack[-1]
                if i < len(adj[v]):
                    stack[-1] = (v, parent, i + 1)
                    w = adj[v][i]
                    if w == parent:
                        continue
                    if w in disc:
                        low[v] = min(low[v], disc[w])
                    else:
                        disc[w] = low[w] = t
                        t += 1
                        if v == root:
                            children += 1
                        stack.append((w, v, 0))
                else:
                    stack.pop()
                    if parent is not None:
                        low[parent] = min(low[parent], low[v])
                        if parent != root and low[v] >= disc[parent]:
                            cut.add(parent)
            if children > 1:
                cut.add(root)
        return sorted(((n, len(adj[n])) for n in cut), key=lambda x: (-x[1], x[0]))

    def metrics(self) -> dict[str, Any]:
        """Scalar health figures, for snapshots and ``--json`` output."""
        comps = self.components()
        return {
            "notes": len(self.notes),
            "note_links": len(self.links),
            "orphans": len(self.orphans()),
            "dead_ends": len(self.dead_ends()),
            "wanted_pages": len(self.wanted),
            "components": len(comps),
            "largest_component": len(comps[0]) if comps else 0,
            "bridges": len(self.bridges()),
            "typed_links": {k: len(v) for k, v in sorted(self.typed.items())},
            "tags": len(self.tags),
            "ambiguous_links": self.ambiguous,
            "frontmatter_errors": len(self.frontmatter_errors),
        }


def vault_health(con: sqlite3.Connection) -> VaultHealth:
    """Read the note graph out of a built store.

    :param con: Connection to the vault's ``graph.sqlite``.
    :return: The vault's health figures.
    """
    rows = con.execute(
        "SELECT id, name, metadata FROM nodes WHERE kind = 'note' ORDER BY id"
    ).fetchall()
    health = VaultHealth(notes=[r[0] for r in rows], titles={})
    for nid, name, meta in rows:
        m = json.loads(meta) if meta else {}
        health.titles[nid] = m.get("title") or name
        if m.get("frontmatter_error"):
            health.frontmatter_errors[nid] = m["frontmatter_error"]

    placeholders = ",".join("?" for _ in NON_LINK_RELS)
    edges = con.execute(
        f"SELECT src, dst, rel, evidence FROM edges WHERE rel NOT IN ({placeholders})",
        NON_LINK_RELS,
    ).fetchall()
    for src, dst, rel, evidence in edges:
        ev = _evidence(evidence)
        if ev.get("ambiguous"):
            health.ambiguous += 1
        if dst.startswith("missing:"):
            health.wanted.setdefault(dst.removeprefix("missing:"), set()).add(src)
            continue
        target = note_of(dst)
        if target is None or target == src:
            continue
        health.links.setdefault((src, target), set()).add(rel)
        health.out_links.setdefault(src, set()).add(target)
        health.in_links.setdefault(target, set()).add(src)
        if rel not in PLAIN_LINK_RELS:
            health.typed.setdefault(rel, []).append((src, target))

    for tag, n in con.execute(
        "SELECT dst, COUNT(DISTINCT src) FROM edges WHERE rel = 'TAGGED' GROUP BY dst"
    ).fetchall():
        health.tags[tag.removeprefix("tag:")] = n
    return health


def _evidence(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        v = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def render_report(health: VaultHealth, stats: dict[str, Any], *, top: int = 15) -> str:
    """Markdown graph-health report.

    :param health: Figures from :func:`vault_health`.
    :param stats: ``VaultKG.stats()`` output, for the counts table.
    :param top: Rows per ranked list.
    :return: Markdown, first line ``# VaultKG Analysis``.
    """

    def label(nid: str) -> str:
        return f"{health.titles.get(nid, nid)} (`{nid.removeprefix('note:')}`)"

    m = health.metrics()
    out = ["# VaultKG Analysis", ""]
    out += [
        f"{m['notes']} notes, {m['note_links']} note-to-note links, "
        f"{m['components']} linked group{'' if m['components'] == 1 else 's'} "
        f"(largest {m['largest_component']}), "
        f"{m['orphans']} orphans, {m['wanted_pages']} wanted pages.",
        "",
        "## Counts",
        "",
        "| kind | nodes |",
        "|---|---|",
    ]
    for k, v in sorted(stats.get("node_counts", {}).items()):
        out.append(f"| {'unresolved' if k == 'symbol' else k} | {v} |")
    out += ["", "| relation | edges |", "|---|---|"]
    for k, v in sorted(stats.get("edge_counts", {}).items()):
        out.append(f"| {k} | {v} |")

    out += ["", "## Hubs", "", "Most-linked notes, by distinct notes linking in.", ""]
    out += [f"1. {label(n)} -- {c}" for n, c in health.hubs(top)] or ["_none_"]

    bridges = health.bridges()
    out += [
        "",
        "## Bridges",
        "",
        "Notes whose removal would split the graph: the only path between two groups.",
        "",
    ]
    out += [f"- {label(n)} -- degree {d}" for n, d in bridges[:top]] or ["_none_"]

    wanted = sorted(health.wanted.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    out += ["", "## Wanted pages", "", "Link targets no note answers to.", ""]
    out += [f"- `{t}` -- linked from {len(s)}" for t, s in wanted[:top]] or ["_none_"]

    orphans = health.orphans()
    out += ["", f"## Orphans ({len(orphans)})", "", "Notes with no link in or out.", ""]
    out += [f"- {label(n)}" for n in orphans[:top]] or ["_none_"]
    if len(orphans) > top:
        out.append(f"- ... and {len(orphans) - top} more")

    comps = health.components()
    if len(comps) > 1:
        out += ["", "## Islands", "", "Linked groups cut off from the largest one.", ""]
        for c in comps[1 : top + 1]:
            out.append(f"- {len(c)} notes: " + ", ".join(label(n) for n in c[:3]))

    if health.typed:
        out += ["", "## Typed links", ""]
        for rel, pairs in sorted(health.typed.items()):
            out.append(f"- **{rel}**: {len(pairs)}")
        for rel in ("CONTRADICTS",):
            for a, b in sorted(health.typed.get(rel, []))[:top]:
                out.append(f"  - {label(a)} contradicts {label(b)}")

    if health.tags:
        out += ["", "## Tags", ""]
        for t, n in sorted(health.tags.items(), key=lambda kv: (-kv[1], kv[0]))[:top]:
            out.append(f"- `#{t}` -- {n} notes")

    if health.ambiguous or health.frontmatter_errors:
        out += ["", "## Warnings", ""]
        if health.ambiguous:
            out.append(
                f"- {health.ambiguous} links matched more than one note of the same name; "
                "the closest was used. Link by path to make them exact."
            )
        for nid, err in sorted(health.frontmatter_errors.items())[:top]:
            out.append(f"- frontmatter in {label(nid)} did not parse: {err}")
    out.append("")
    return "\n".join(out)
