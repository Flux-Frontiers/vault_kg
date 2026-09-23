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
        at = r["via"].partition("#")[2] if r["via"].startswith("heading:") and backlinks else ""
        click.echo(
            f"{r['rel']:<12} {'<-' if backlinks else '->'} {r['node']}"
            + (f"  (#{at})" if at else "")
        )


_VIZ_EXTRA = 'pip install "vault-kg[viz]"'
_VIZ3D_EXTRA = 'pip install "vault-kg[viz3d]"'

group_by_option = click.option(
    "--group-by",
    type=click.Choice(["auto", "folder", "tag"]),
    default="auto",
    show_default=True,
    help="Limbs from folders, or from nested tags. auto uses tags only for a flat vault.",
)
color_by_option = click.option(
    "--color-by",
    type=click.Choice(["group", "tag", "links"]),
    default="group",
    show_default=True,
    help="Colour leaves by top-level group, by first tag, or by backlink count.",
)
preset_option = click.option(
    "--preset", default="16-landscape", show_default=True, help="Looking Glass quilt preset."
)
schematic_option = click.option(
    "--schematic",
    is_flag=True,
    help="Draw the straight-line layout instead of growing organic wood (fast at any size).",
)


@cli.command()
@vault_option
@click.argument("root", required=False)
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="HTML file to write.  [default: <vault name>_links.html]",
)
@click.option(
    "--hops",
    default=1,
    show_default=True,
    type=click.IntRange(0, MAX_HOP),
    help="Links to expand from ROOT.",
)
@click.option(
    "--max-nodes",
    default=200,
    show_default=True,
    type=click.IntRange(2, 5000),
    help="Node budget; beyond a few hundred the graph stops being readable.",
)
@click.option("--headings", is_flag=True, help="Draw headings as well as notes.")
def viz(
    vault: str, root: str | None, output: Path | None, hops: int, max_nodes: int, headings: bool
) -> None:
    """Write the link graph as a self-contained interactive HTML page.

    With ROOT (a node id or a note's vault path), draw that note's
    neighbourhood; without it, the most connected part of the vault. Notes
    are sized by backlinks.
    """
    if importlib.util.find_spec("pyvis") is None:
        raise click.UsageError(f"viz needs pyvis. Install with:  {_VIZ_EXTRA}")
    from vaultkg import viz as render  # noqa: PLC0415 -- viz-extra import boundary

    kinds = render.ALL_KINDS if headings else render.DEFAULT_KINDS
    with _open(vault) as kg:
        try:
            html, n_nodes, n_edges = render.link_graph_html(
                kg, root=root, hops=hops, max_nodes=max_nodes, kinds=kinds
            )
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
        path = output or Path(f"{kg.repo_root.name}_links.html")
    path.write_text(html, encoding="utf-8")
    click.echo(f"Wrote {path} -- {n_nodes} nodes, {n_edges} edges.")


@cli.command()
@vault_option
@preset_option
@click.option(
    "-o",
    "--out",
    "out_dir",
    default="renders",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Output directory for the quilt.",
)
@group_by_option
@color_by_option
@click.option(
    "--tip-radius", default=0.06, show_default=True, type=float, help="Twig radius, world units."
)
@click.option("--leaf-size", default=0.35, show_default=True, type=float, help="Leaf radius.")
@click.option(
    "--zoom",
    default=1.0,
    show_default=True,
    type=float,
    help="Camera dolly after framing. >1 fills more of the tile, driving more depth.",
)
@click.option(
    "--fov",
    default=14.0,
    show_default=True,
    type=float,
    help="Per-view vertical field of view in degrees; Looking Glass recommends ~14.",
)
@click.option("--cast", is_flag=True, help="Send the finished quilt to Looking Glass Bridge.")
@schematic_option
def quilt(
    vault: str,
    preset: str,
    out_dir: Path,
    group_by: str,
    color_by: str,
    tip_radius: float,
    leaf_size: float,
    zoom: float,
    fov: float,
    cast: bool,
    schematic: bool,
) -> None:
    """Grow the vault as a 3-D tree and render it as a Looking Glass quilt.

    The vault is the trunk, folders are limbs, notes are leaves.
    """
    try:
        import pyvista as pv  # noqa: PLC0415 -- viz3d-extra import boundary
        from quiltwright import (  # noqa: PLC0415
            QUILT_PRESETS,
            depth_report,
            render_quilt,
            save_quilt,
        )
    except ImportError as exc:
        raise click.UsageError(
            f"quilt needs pyvista and quiltwright. Install with:  {_VIZ3D_EXTRA}"
        ) from exc
    from kg_utils.viz3d import frame_tree  # noqa: PLC0415

    from vaultkg import scene as render3d  # noqa: PLC0415

    if preset not in QUILT_PRESETS:
        raise click.UsageError(
            f"unknown quilt preset {preset!r}. Choose from: {', '.join(QUILT_PRESETS)}"
        )
    spec = QUILT_PRESETS[preset]

    plotter = pv.Plotter(off_screen=True)
    with _open(vault) as kg:
        name = kg.repo_root.name
        try:
            tree = render3d.build_vault_tree_scene(
                kg,
                plotter,
                group_by=group_by,
                color_by=color_by,
                tip_radius=tip_radius,
                leaf_size=leaf_size,
                organic=not schematic,
            )
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
    click.echo(f"Scene: {tree.title}")
    click.echo("Legend: " + ", ".join(f"{k} {c}" for k, c in tree.legend.items()))

    frame = frame_tree(tree.points, fov=fov)
    plotter.camera.position = frame.position
    plotter.camera.focal_point = frame.focal_point
    plotter.camera.up = frame.up
    plotter.reset_camera()  # ty: ignore[missing-argument]
    click.echo(
        depth_report(
            plotter,
            spec,
            fov=fov,
            zoom=zoom,
            labels=("nearest foliage", "focal plane (display surface)", "farthest foliage"),
        )
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"Rendering {spec.n_views} views at {spec.tile_width}x{spec.tile_height}...")
    path = save_quilt(render_quilt(plotter, spec, fov=fov, zoom=zoom), out_dir / name, spec)
    plotter.close()
    click.echo(f"Wrote {path}")

    if cast:
        from quiltwright import cast_quilt  # noqa: PLC0415

        try:
            cast_quilt(path.resolve(), spec)
            click.echo("Cast to Looking Glass Bridge.")
        except Exception as exc:  # noqa: BLE001 -- no Bridge must not fail the render
            click.echo(f"Cast failed (is Looking Glass Bridge running?): {exc}", err=True)


@cli.command()
@vault_option
@group_by_option
@color_by_option
@preset_option
@click.option("--width", default=1400, show_default=True, type=int, help="Window width, pixels.")
@click.option("--height", default=900, show_default=True, type=int, help="Window height, pixels.")
@schematic_option
def viz3d(
    vault: str,
    group_by: str,
    color_by: str,
    preset: str,
    width: int,
    height: int,
    schematic: bool,
) -> None:
    """Open the vault as a 3-D tree in an interactive viewer.

    Orbit, zoom and pan with the mouse. The toolbar's Cast to Looking Glass
    button sends the current view to Bridge.
    """
    if importlib.util.find_spec("PyQt5") is None or importlib.util.find_spec("pyvistaqt") is None:
        raise click.UsageError(f"viz3d needs PyQt5 and pyvistaqt. Install with:  {_VIZ3D_EXTRA}")
    with _open(vault) as kg:
        root = kg.repo_root
    from vaultkg import viz3d as viewer  # noqa: PLC0415 -- viz3d-extra import boundary

    try:
        viewer.launch(
            root,
            group_by=group_by,
            color_by=color_by,
            preset=preset,
            organic=not schematic,
            width=width,
            height=height,
        )
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc


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
