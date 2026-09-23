"""The 2-D link graph (``vaultkg viz``) and the import boundary around it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from vaultkg.cli import cli
from vaultkg.module import VaultKG
from vaultkg.theme import CATEGORY_PALETTE, OTHER_COLOR, ROOT_LABEL, category_colors, top_folder

RETRIEVAL = "note:wiki/concepts/Retrieval.md"


@pytest.fixture
def graph(vault: Path):
    kg = VaultKG(vault)
    kg.build_graph(wipe=True)
    yield kg
    kg.close()


def test_importing_the_package_and_cli_pulls_no_render_stack() -> None:
    # A bare install must work: the render stacks arrive only with the extras,
    # and the CLI imports them inside the commands that need them.
    code = (
        "import sys, vaultkg, vaultkg.cli, vaultkg.mcp_server, vaultkg.theme\n"
        "heavy = {'pyvis', 'pyvista', 'PyQt5', 'pyvistaqt', 'quiltwright', 'plotly'}\n"
        "print(sorted(heavy & set(sys.modules)))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_category_colors_fold_the_tail_into_other() -> None:
    names = [f"f{i}" for i in range(len(CATEGORY_PALETTE) + 2)]
    colors = category_colors(names)
    assert [colors[n] for n in names[: len(CATEGORY_PALETTE)]] == list(CATEGORY_PALETTE)
    assert colors[names[-1]] == OTHER_COLOR


def test_top_folder() -> None:
    assert top_folder("wiki/concepts/X.md") == "wiki"
    assert top_folder("Home.md") == ROOT_LABEL


pyvis = pytest.importorskip("pyvis")

from vaultkg import viz  # noqa: E402 -- after the importorskip


def test_whole_vault_graph(graph: VaultKG) -> None:
    html, n_nodes, n_edges = viz.link_graph_html(graph)
    assert html.lstrip().lower().startswith("<html") or "<html" in html.lower()
    assert n_nodes > 0 and n_edges > 0
    assert "Retrieval augmented generation" in html or "Retrieval" in html
    # Headings are opt-in.
    assert "heading:" not in html


def test_rooted_graph_highlights_the_root_and_keeps_backlinks(graph: VaultKG) -> None:
    html, n_nodes, _ = viz.link_graph_html(graph, root="wiki/concepts/Retrieval", hops=1)
    assert "#FFD700" in html  # the root's highlight border
    assert "note:index.md" in html  # links *to* the root are part of its neighbourhood
    assert n_nodes <= 200


def test_max_nodes_is_a_hard_budget(graph: VaultKG) -> None:
    _, n_nodes, _ = viz.link_graph_html(graph, max_nodes=3)
    assert n_nodes == 3


def test_headings_can_be_drawn(graph: VaultKG) -> None:
    # "Failure modes" sits under the note's H1, two CONTAINS hops from the note.
    html, _, _ = viz.link_graph_html(graph, root=RETRIEVAL, hops=2, kinds=viz.ALL_KINDS)
    assert "heading:wiki/concepts/Retrieval.md#failure-modes" in html


def test_notes_are_coloured_by_top_folder(graph: VaultKG) -> None:
    theme = viz.vault_theme(["LINKS_TO", "SUPPORTS", "WHATEVER"], ["wiki", ROOT_LABEL])
    wiki = {"id": RETRIEVAL, "kind": "note", "module_path": "wiki/concepts/Retrieval.md"}
    root = {"id": "note:index.md", "kind": "note", "module_path": "index.md"}
    assert theme.style_of(wiki).color == CATEGORY_PALETTE[0]
    assert theme.style_of(root).color == CATEGORY_PALETTE[1]
    assert theme.relations["WHATEVER"] == viz.TYPED_REL_COLOR


def test_backlink_scores_rank_the_hub_first(graph: VaultKG) -> None:
    scores = viz.backlink_scores(graph)
    assert scores.ranks[RETRIEVAL] == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"root": "no/such/note"}, "no such node"),
        ({"kinds": ("note", "planet")}, "unknown kind"),
    ],
)
def test_bad_arguments(graph: VaultKG, kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        viz.link_graph_html(graph, **kwargs)


def test_cli_viz_writes_the_page(graph: VaultKG, tmp_path: Path) -> None:
    vault = str(graph.repo_root)
    graph.close()
    out = tmp_path / "links.html"
    runner = CliRunner()
    r = runner.invoke(cli, ["viz", "--vault", vault, "wiki/concepts/Retrieval", "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert out.exists() and "Wrote" in r.output and "nodes" in r.output
    r = runner.invoke(cli, ["viz", "--vault", vault, "nowhere"])
    assert r.exit_code == 2 and "no such node" in r.output


def test_cli_viz_defaults_to_a_file_named_for_the_vault(
    graph: VaultKG, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = str(graph.repo_root)
    graph.close()
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(cli, ["viz", "--vault", vault, "--headings"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "vault_links.html").exists()


def test_cli_viz_without_the_extra_says_how_to_install(
    graph: VaultKG, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util  # noqa: PLC0415

    vault = str(graph.repo_root)
    graph.close()
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda n, *a: None if n == "pyvis" else real(n, *a)
    )
    r = CliRunner().invoke(cli, ["viz", "--vault", vault])
    assert r.exit_code == 2 and 'pip install "vault-kg[viz]"' in r.output
