"""The 3-D vault tree: placement (NumPy only), composition, quilt and viewer."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

from vaultkg import scene
from vaultkg.cli import cli
from vaultkg.module import VaultKG
from vaultkg.theme import ROOT_LABEL

RETRIEVAL = "note:wiki/concepts/Retrieval.md"


@pytest.fixture
def graph(vault: Path):
    kg = VaultKG(vault)
    kg.build_graph(wipe=True)
    yield kg
    kg.close()


def _notes(graph: VaultKG) -> list[dict]:
    return graph.store.query_nodes(kinds=["note"])


# ---------------------------------------------------------------- placement


def test_folders_become_limbs_and_notes_sit_at_their_tip(graph: VaultKG) -> None:
    pos = scene.vault_tree_positions(_notes(graph))
    assert pos.group_by == "folder"
    assert {"wiki", "wiki/concepts", "wiki/sources", "projects", "projects/p1"} <= set(
        pos.limb_tips
    )
    assert pos.limb_parent["wiki/concepts"] == "wiki"
    assert pos.limb_parent["wiki"] == ""
    assert set(pos.note_positions) == {n["id"] for n in _notes(graph)}
    # A note clusters near its own folder's tip, not another folder's.
    tip = pos.limb_tips["wiki/concepts"]
    near = np.linalg.norm(pos.note_positions[RETRIEVAL] - tip)
    far = np.linalg.norm(pos.note_positions[RETRIEVAL] - pos.limb_tips["projects/p1"])
    assert near < far


def test_subfolders_branch_higher_and_further_than_their_parent(graph: VaultKG) -> None:
    pos = scene.vault_tree_positions(_notes(graph))
    parent, child = pos.limb_tips["wiki"], pos.limb_tips["wiki/concepts"]
    assert child[2] > parent[2]
    assert np.hypot(child[0], child[1]) > np.hypot(parent[0], parent[1])


def test_root_notes_ring_the_base_above_ground(graph: VaultKG) -> None:
    pos = scene.vault_tree_positions(_notes(graph))
    for nid in ("note:index.md", "note:Orphan.md"):
        assert pos.note_group[nid] == ""
        assert 0 < pos.note_positions[nid][2] < pos.trunk_height * 0.25


def test_placement_is_deterministic(graph: VaultKG) -> None:
    a = scene.vault_tree_positions(_notes(graph))
    b = scene.vault_tree_positions(list(reversed(_notes(graph))))
    for nid, p in a.note_positions.items():
        assert np.allclose(p, b.note_positions[nid])


def test_a_flat_vault_grows_from_nested_tags() -> None:
    notes = [
        {"id": "note:a.md", "module_path": "a.md", "metadata": {"tags": ["ml/retrieval"]}},
        {"id": "note:b.md", "module_path": "b.md", "metadata": {"tags": ["ml"]}},
        {"id": "note:c.md", "module_path": "c.md", "metadata": {}},
    ]
    pos = scene.vault_tree_positions(notes)
    assert pos.group_by == "tag"
    assert set(pos.limb_tips) == {"ml", "ml/retrieval"}
    assert pos.note_group["note:c.md"] == ""
    forced = scene.vault_tree_positions(notes, group_by="folder")
    assert forced.group_by == "folder" and not forced.limb_tips


def test_placement_rejects_an_empty_vault_and_bad_options() -> None:
    with pytest.raises(ValueError, match="no notes"):
        scene.vault_tree_positions([])
    with pytest.raises(ValueError, match="group_by"):
        scene.vault_tree_positions([{"id": "note:a.md", "module_path": "a.md"}], group_by="x")


@pytest.mark.parametrize("color_by", ["group", "tag", "links"])
def test_leaf_colors_index_their_palette(graph: VaultKG, color_by: str) -> None:
    pos = scene.vault_tree_positions(_notes(graph))
    ids = list(pos.note_positions)
    codes, palette, legend = scene.leaf_colors(graph, ids, pos, color_by=color_by)
    assert len(codes) == len(ids)
    assert codes.min() >= 0 and codes.max() < len(palette)
    assert legend
    if color_by == "group":
        assert {"wiki", ROOT_LABEL} <= set(legend)
    with pytest.raises(ValueError, match="color_by"):
        scene.leaf_colors(graph, ids, pos, color_by="mood")


def test_leaf_scales_follow_backlinks(graph: VaultKG) -> None:
    ids = [RETRIEVAL, "note:Orphan.md", "note:wiki/concepts/Search.md"]
    scales = scene.leaf_scales(graph, ids, size_by="links")
    backlinks = graph.health().in_links
    assert len(backlinks[RETRIEVAL]) > len(backlinks["note:wiki/concepts/Search.md"])
    assert scales[0] > scales[2] > scales[1]  # hub > linked > orphan
    assert scales[1] == pytest.approx(scene.LEAF_SCALE_BASE)
    assert scales.max() <= scene.LEAF_SCALE_MAX
    assert (scene.leaf_scales(graph, ids, size_by="none") == 1.0).all()
    with pytest.raises(ValueError, match="size_by"):
        scene.leaf_scales(graph, ids, size_by="mass")


# ---------------------------------------------------------------- composition

pv = pytest.importorskip("pyvista")


@pytest.mark.parametrize("organic", [True, False])
def test_scene_composes_wood_and_leaves(graph: VaultKG, organic: bool) -> None:
    plotter = pv.Plotter(off_screen=True)
    try:
        tree = scene.build_vault_tree_scene(graph, plotter, organic=organic)
        assert {"wood", "leaves"} <= set(plotter.actors)
        assert tree.counts["notes"] == 8
        assert tree.points.shape[1] == 3 and len(tree.points)
        assert ("organic" if organic else "schematic") in tree.title
    finally:
        plotter.close()


def test_cli_quilt_renders_and_names_the_file(
    graph: VaultKG, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("quiltwright")
    vault = str(graph.repo_root)
    graph.close()
    cast: list[Path] = []
    monkeypatch.setattr("quiltwright.cast_quilt", lambda path, spec: cast.append(path))
    r = CliRunner().invoke(
        cli,
        ["quilt", "--vault", vault, "--preset", "portrait", "-o", str(tmp_path), "--schematic"]
        + ["--color-by", "links", "--cast"],
    )
    assert r.exit_code == 0, r.output
    written = list(tmp_path.glob("vault_qs*.png"))
    assert len(written) == 1
    assert "Legend: 0 backlinks" in r.output and "focal plane" in r.output
    assert cast == [written[0].resolve()]


@pytest.mark.parametrize("organic", [True, False])
def test_leaf_size_follows_backlinks_in_the_scene(graph: VaultKG, organic: bool) -> None:
    """A hub's leaf is drawn bigger than an orphan's, in both render modes."""
    sizes = {}
    for size_by in ("links", "none"):
        plotter = pv.Plotter(off_screen=True)
        try:
            scene.build_vault_tree_scene(graph, plotter, size_by=size_by, organic=organic)
            leaves = plotter.actors["leaves"].mapper.dataset
            sizes[size_by] = float(np.ptp(leaves.points, axis=0).max())
        finally:
            plotter.close()
    # Sized leaves change the extent of the foliage; uniform ones do not match it.
    assert not np.isclose(sizes["links"], sizes["none"])


def test_cli_quilt_reports_a_failed_cast_without_failing(
    graph: VaultKG, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("quiltwright")
    vault = str(graph.repo_root)
    graph.close()

    def no_bridge(path: Path, spec: object) -> None:
        raise ConnectionError("refused")

    monkeypatch.setattr("quiltwright.cast_quilt", no_bridge)
    r = CliRunner().invoke(
        cli,
        ["quilt", "--vault", vault, "--preset", "portrait", "-o", str(tmp_path)]
        + ["--schematic", "--cast", "--size-by", "none"],
    )
    assert r.exit_code == 0, r.output
    assert "Cast failed" in r.output


def test_cli_quilt_rejects_an_unknown_preset(graph: VaultKG) -> None:
    pytest.importorskip("quiltwright")
    vault = str(graph.repo_root)
    graph.close()
    r = CliRunner().invoke(cli, ["quilt", "--vault", vault, "--preset", "bogus"])
    assert r.exit_code == 2 and "unknown quilt preset" in r.output


# ---------------------------------------------------------------- viewer


@pytest.fixture(scope="module")
def qapp():
    """One offscreen QApplication for the module."""
    pytest.importorskip("PyQt5")
    pytest.importorskip("pyvistaqt")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication  # noqa: PLC0415

    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("off_screen", [False, True])
def test_the_viewer_window_builds(
    qapp, graph: VaultKG, monkeypatch: pytest.MonkeyPatch, off_screen: bool
) -> None:
    # CI's headless-display action sets PYVISTA_OFF_SCREEN, which a developer
    # machine does not; connectome_kg's viewer passed locally and failed there.
    monkeypatch.setattr(pv, "OFF_SCREEN", off_screen)
    from vaultkg.viz3d import VaultTreeWindow  # noqa: PLC0415

    window = VaultTreeWindow(graph, organic=False)
    try:
        assert "VaultKG viz3d" in window.windowTitle()
        assert "notes=8" in window.windowTitle()
    finally:
        window.close()


def test_the_cast_action_reports_the_result(
    qapp, graph: VaultKG, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kg_utils.viz3d.qt import CastResult  # noqa: PLC0415

    from vaultkg import viz3d  # noqa: PLC0415

    calls: list[object] = []
    shown: list[str] = []
    result = CastResult(path=Path("x.png"), error=None, elapsed=0.1, message="sent")

    def fake_cast(build, camera, out_stem, spec):
        plotter = pv.Plotter(off_screen=True)
        build(plotter)  # the stored builder must compose a scene on its own
        plotter.close()
        calls.append(out_stem)
        return result

    monkeypatch.setattr(viz3d, "cast_scene_to_looking_glass", fake_cast)
    monkeypatch.setattr(viz3d.QMessageBox, "information", lambda *a: shown.append(a[2]))
    window = viz3d.VaultTreeWindow(graph, organic=False)
    try:
        window._cast()
    finally:
        window.close()
    assert calls == [Path("renders") / "vault_cast"]
    assert shown == [result.message]


def test_cli_viz3d_launches_the_viewer(graph: VaultKG, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PyQt5")
    pytest.importorskip("pyvistaqt")
    from vaultkg import viz3d  # noqa: PLC0415

    vault = graph.repo_root
    graph.close()
    seen: dict = {}
    monkeypatch.setattr(viz3d, "launch", lambda root, **kw: seen.update(root=root, **kw))
    r = CliRunner().invoke(cli, ["viz3d", "--vault", str(vault), "--schematic"])
    assert r.exit_code == 0, r.output
    assert seen["root"] == vault.resolve() and seen["organic"] is False
    assert seen["size_by"] == "links"


def test_launch_opens_a_sized_window(qapp, graph: VaultKG, monkeypatch: pytest.MonkeyPatch) -> None:
    from PyQt5.QtWidgets import QApplication  # noqa: PLC0415

    from vaultkg import viz3d  # noqa: PLC0415

    vault = graph.repo_root
    graph.close()
    shown: list[tuple[int, int]] = []

    def no_loop(self) -> int:
        for w in self.topLevelWidgets():
            if isinstance(w, viz3d.VaultTreeWindow):
                shown.append((w.width(), w.height()))
                w.close()
        return 0

    monkeypatch.setattr(QApplication, "exec_", no_loop)
    viz3d.launch(vault, organic=False, width=640, height=480)
    assert shown == [(640, 480)]
