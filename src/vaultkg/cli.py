"""cli.py -- the ``vaultkg`` command line.

``vaultkg build`` parses the vault into ``<vault>/.vaultkg/``; ``analyze``
prints the graph-health report; ``query`` and ``pack`` search it (these need
the ``semantic`` extra and a build without ``--no-index``).
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import click
from kg_utils.validation import MAX_HOP, MAX_K
from kg_utils.vector_backend import VectorStoreNotFoundError

from vaultkg.module import MAX_LIMIT, VaultKG


def _open(vault: str) -> VaultKG:
    kg = VaultKG(vault)
    if not kg.db_path.exists():
        raise click.ClickException(f"no graph at {kg.db_path}; run `vaultkg build` first")
    return kg


#: Top-level modules the ``semantic`` extra installs for query and pack.
_SEMANTIC_MODULES = frozenset({"sentence_transformers", "torch", "transformers", "sqlite_vec"})


def _missing_semantic() -> list[str]:
    """The ``semantic`` extra's modules that are not installed."""
    return sorted(m for m in _SEMANTIC_MODULES if importlib.util.find_spec(m) is None)


@contextmanager
def _search_errors() -> Iterator[None]:
    """Turn the ways a search can fail before it starts into CLI errors."""
    try:
        yield
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc
    except ModuleNotFoundError as exc:
        if (exc.name or "").split(".")[0] not in _SEMANTIC_MODULES:
            raise
        raise click.ClickException(
            f"query and pack need the semantic extra ({exc.name} is not installed): "
            'pip install "vault-kg[semantic]"'
        ) from exc
    except VectorStoreNotFoundError as exc:
        raise click.ClickException(
            "no vector index; run `vaultkg build` without --no-index first"
        ) from exc


vault_option = click.option(
    "--vault",
    default=".",
    show_default=True,
    type=click.Path(exists=True, file_okay=False),
    help="Vault root directory.",
)


@click.group()
@click.version_option(package_name="vault-kg")
def cli() -> None:
    """vaultkg -- an Obsidian vault as a deterministic knowledge graph."""


@cli.command()
@vault_option
@click.option(
    "--exclude",
    multiple=True,
    metavar="PATTERN",
    help="Directory name or glob to skip (repeatable). Dot-folders are always skipped.",
)
@click.option("--no-index", is_flag=True, help="Build the graph only; skip embeddings.")
@click.option("--wipe/--no-wipe", default=True, show_default=True, help="Rebuild from scratch.")
def build(vault: str, exclude: tuple[str, ...], no_index: bool, wipe: bool) -> None:
    """Parse the vault into a graph (and a vector index)."""
    # Checked up front: the index is built last, after the whole graph.
    if not no_index and (missing := _missing_semantic()):
        raise click.UsageError(
            f"the vector index needs the semantic extra (missing {', '.join(missing)}); "
            'pip install "vault-kg[semantic]", or pass --no-index'
        )
    with VaultKG(vault, exclude=exclude) as kg:
        if no_index:
            # The SDK's build_graph() leaves any existing index alone. After a
            # graph-only rebuild that index describes the previous graph, so
            # query would seed from notes that may be gone; remove it instead.
            stale = [
                p
                for p in (
                    kg.vectors_path,
                    *kg.vectors_path.parent.glob(kg.vectors_path.name + "-*"),
                )
                if p.exists()
            ]
            for p in stale:
                p.unlink()
            stats = kg.build_graph(wipe=wipe)
        else:
            stale = []
            stats = kg.build(wipe=wipe)
    click.echo(str(stats))
    if stale:
        click.echo("removed the stale vector index; run `vaultkg build` to rebuild it")


@cli.command()
@vault_option
@click.option("--json", "as_json", is_flag=True, help="Print health metrics as JSON.")
def analyze(vault: str, as_json: bool) -> None:
    """Graph-health report: hubs, bridges, orphans, wanted pages, islands."""
    with _open(vault) as kg:
        if as_json:
            click.echo(json.dumps(kg.health().metrics(), indent=2))
        else:
            click.echo(kg.analyze())


@cli.command()
@vault_option
def stats(vault: str) -> None:
    """Node and edge counts."""
    with _open(vault) as kg:
        click.echo(json.dumps(kg.stats(), indent=2))


@cli.command()
@vault_option
@click.argument("q")
@click.option("-k", default=8, show_default=True, type=click.IntRange(1, MAX_K), help="Seed hits.")
@click.option(
    "--hop", default=1, show_default=True, type=click.IntRange(0, MAX_HOP), help="Link hops."
)
@click.option("--json", "as_json", is_flag=True, help="Print the full result as JSON.")
def query(vault: str, q: str, k: int, hop: int, as_json: bool) -> None:
    """Search notes and sections, then follow their links."""
    with _open(vault) as kg, _search_errors():
        res = kg.query(q, k=k, hop=hop)
    if as_json:
        click.echo(res.to_json())
        return
    for n in res.nodes:
        rel = n.get("relevance", {})
        click.echo(
            f"{rel.get('semantic', 0):.3f}  hop{rel.get('hop', 0)}  {n['kind']:<8} {n['id']}"
        )


@cli.command()
@vault_option
@click.argument("q")
@click.option("-k", default=8, show_default=True, type=click.IntRange(1, MAX_K), help="Seed hits.")
@click.option(
    "--hop", default=1, show_default=True, type=click.IntRange(0, MAX_HOP), help="Link hops."
)
def pack(vault: str, q: str, k: int, hop: int) -> None:
    """Search and print the matching note text as Markdown."""
    with _open(vault) as kg, _search_errors():
        click.echo(kg.pack(q, k=k, hop=hop).to_markdown())


@cli.command()
@vault_option
@click.argument("node_id")
@click.option("--in", "backlinks", is_flag=True, help="Show backlinks instead of outgoing links.")
@click.option("--rel", default="", help="Only this relation (LINKS_TO, SUPPORTS...).")
@click.option("--limit", default=50, show_default=True, type=click.IntRange(1, MAX_LIMIT))
def links(vault: str, node_id: str, backlinks: bool, rel: str, limit: int) -> None:
    """Links at NODE_ID (a node id or a note's vault path); --in for backlinks."""
    direction = "in" if backlinks else "out"
    with _open(vault) as kg:
        try:
            rows = kg.links(node_id, direction=direction, rel=rel, limit=limit)
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
    for r in rows:
        click.echo(f"{r['rel']:<12} {'<-' if backlinks else '->'} {r['node']}")


@cli.group()
def snapshot() -> None:
    """Point-in-time metric snapshots of the built graph."""


def _manager(vault: str):
    from vaultkg.snapshots import SnapshotManager  # noqa: PLC0415 -- CLI-only

    store = Path(vault) / VaultKG._default_dir
    return SnapshotManager(store / "snapshots", db_path=store / "graph.sqlite")


@snapshot.command("save")
@vault_option
@click.argument("key", default="", required=False)
@click.option("--force", is_flag=True, help="Save even if metrics are unchanged.")
def snapshot_save(vault: str, key: str, force: bool) -> None:
    """Save a snapshot keyed on KEY (default: a UTC timestamp)."""
    mgr = _manager(vault)
    with _open(vault) as kg:
        stats = kg.stats()
    snap = mgr.capture(
        graph_stats_dict=stats, key=key, subject=f"corpus:{Path(vault).resolve().name}"
    )
    path = mgr.save_snapshot(snap, force=force)
    click.echo(f"saved {path}" if path else "unchanged since the last snapshot; nothing saved")


@snapshot.command("list")
@vault_option
def snapshot_list(vault: str) -> None:
    """List snapshots, newest first."""
    for s in _manager(vault).list_snapshots():
        m = s.get("metrics", {})
        click.echo(
            f"{s['key'][:32]:<32} notes {m.get('notes', 0):>6}  links {m.get('note_links', 0):>7}"
            f"  orphans {m.get('orphans', 0):>5}  wanted {m.get('wanted_pages', 0):>5}"
        )


@snapshot.command("diff")
@vault_option
@click.argument("a")
@click.argument("b")
def snapshot_diff(vault: str, a: str, b: str) -> None:
    """Compare two snapshots."""
    click.echo(json.dumps(_manager(vault).diff_snapshots(a, b), indent=2, default=str))


if __name__ == "__main__":
    cli()
