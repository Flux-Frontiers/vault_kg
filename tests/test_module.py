"""VaultKG end to end: build, health report, query and pack with a stub embedder."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from tests.conftest import HashEmbedder
from vaultkg.cli import cli
from vaultkg.module import VaultKG, normalize_node_id

RETRIEVAL = "note:wiki/concepts/Retrieval.md"


@pytest.fixture
def built(vault: Path):
    kg = VaultKG(vault)
    kg._embedder = HashEmbedder()
    kg.build(wipe=True)
    yield kg
    kg.close()


def test_builder_version_stamp(built: VaultKG) -> None:
    rows = dict(built.store.con.execute("SELECT key, value FROM _kgrag_meta"))
    assert rows["builder_name"] == "vault_kg"
    assert rows["builder_version"] and rows["built_at"]


def test_stats(built: VaultKG) -> None:
    s = built.stats()
    assert s["notes"] == 8
    assert s["unresolved"] == 2
    assert "function_count" not in s


def test_relations_include_typed(built: VaultKG) -> None:
    rels = built.relations()
    assert rels[:2] == ("CONTAINS", "LINKS_TO")
    assert {"SUPPORTS", "EXTENDS", "CONTRADICTS"} <= set(rels)


def test_health(built: VaultKG) -> None:
    h = built.health()
    assert h.hubs(1)[0][0] == RETRIEVAL
    assert "note:Orphan.md" in h.orphans()
    assert set(h.wanted) == {"nowhere", "long context replaces rag"}
    assert h.ambiguous >= 1
    m = h.metrics()
    assert m["typed_links"]["SUPPORTS"] == 1


def test_bridges() -> None:
    from vaultkg.analysis import VaultHealth  # noqa: PLC0415

    # a - b - c : b is the only path between a and c.
    h = VaultHealth(notes=["a", "b", "c"], titles={})
    h.links = {("a", "b"): {"LINKS_TO"}, ("b", "c"): {"LINKS_TO"}}
    assert h.bridges() == [("b", 2)]
    assert len(h.components()) == 1


def test_analyze_report(built: VaultKG) -> None:
    report = built.analyze()
    assert report.startswith("# VaultKG Analysis")
    for section in ("## Hubs", "## Wanted pages", "## Orphans", "## Typed links"):
        assert section in report


def test_query_follows_links(built: VaultKG) -> None:
    res = built.query("models ignore the middle of long contexts", k=2, hop=1)
    ids = [n["id"] for n in res.nodes]
    assert "note:wiki/sources/Lost in the Middle.md" in ids[:3]
    assert all(n["kind"] != "symbol" for n in res.nodes)


def test_pack_has_note_text(built: VaultKG) -> None:
    pack = built.pack("models ignore the middle of long contexts", k=2, hop=0)
    texts = [n["snippet"]["text"] for n in pack.nodes if n.get("snippet")]
    assert any("Models ignore the middle" in t for t in texts)


def test_cli_build_and_analyze(vault: Path) -> None:
    runner = CliRunner()
    r = runner.invoke(cli, ["build", "--vault", str(vault), "--no-index"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(cli, ["analyze", "--vault", str(vault)])
    assert r.exit_code == 0 and "# VaultKG Analysis" in r.output
    r = runner.invoke(cli, ["snapshot", "save", "--vault", str(vault), "v1"])
    assert r.exit_code == 0, r.output


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("note:wiki/X.md", "note:wiki/X.md"),
        ("heading:a.md#b", "heading:a.md#b"),
        ("wiki/X", "note:wiki/X.md"),
        ("/wiki/X.md", "note:wiki/X.md"),
        (" `tag:ml` ", "tag:ml"),
        ("'missing:nowhere'", "missing:nowhere"),
    ],
)
def test_normalize_node_id(raw: str, expected: str) -> None:
    assert normalize_node_id(raw) == expected


def test_normalize_node_id_rejects_empty_and_long() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        normalize_node_id(" `` ")
    with pytest.raises(ValueError, match="at most 500"):
        normalize_node_id("x" * 501)


def test_links_out_in_and_filtered(built: VaultKG) -> None:
    out = built.links("wiki/concepts/Retrieval")
    assert {"TAGGED", "CONTAINS", "LINKS_TO", "EXTENDS"} <= {r["rel"] for r in out}
    missing = [r for r in out if r["node"] == "missing:nowhere"]
    assert missing and missing[0]["kind"] == "symbol"
    back = built.links(RETRIEVAL, direction="in", rel="links_to")
    assert {r["rel"] for r in back} == {"LINKS_TO"}
    assert "note:index.md" in {r["node"] for r in back}
    assert len(built.links(RETRIEVAL, limit=1)) == 1


def test_links_rejects_bad_arguments(built: VaultKG) -> None:
    with pytest.raises(ValueError, match="direction"):
        built.links(RETRIEVAL, direction="both")
    with pytest.raises(ValueError, match="limit"):
        built.links(RETRIEVAL, limit=501)


def test_node_by_path(built: VaultKG) -> None:
    node = built.node("wiki/concepts/Retrieval.md")
    assert node is not None and node["id"] == RETRIEVAL


def test_analyze_never_raises(built: VaultKG, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise RuntimeError("broken")

    monkeypatch.setattr(built, "health", boom)
    assert "Analysis failed: broken" in built.analyze()


def test_cli_query_pack_links_stats(built: VaultKG) -> None:
    vault = str(built.repo_root)
    built.close()
    runner = CliRunner()

    # The CLI builds its own VaultKG, which would load the real embedding
    # model; hand it the stub instead.
    def stubbed(*args: object, **kwargs: object) -> VaultKG:
        kg = VaultKG(*args, **kwargs)  # type: ignore[arg-type]
        kg._embedder = HashEmbedder()
        return kg

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("vaultkg.cli.VaultKG", stubbed)
        r = runner.invoke(cli, ["query", "--vault", vault, "-k", "2", "long contexts"])
        assert r.exit_code == 0, r.output
        assert "note" in r.output
        r = runner.invoke(cli, ["query", "--vault", vault, "--json", "long contexts"])
        assert r.exit_code == 0 and '"nodes"' in r.output
        r = runner.invoke(cli, ["pack", "--vault", vault, "-k", "2", "long contexts"])
        assert r.exit_code == 0 and "Models ignore the middle" in r.output
    r = runner.invoke(cli, ["links", "--vault", vault, "--in", "wiki/concepts/Retrieval"])
    assert r.exit_code == 0 and "<- note:index.md" in r.output
    r = runner.invoke(cli, ["links", "--vault", vault, "--limit", "0", "x"])
    assert r.exit_code != 0 and "0 is not in the range" in r.output
    r = runner.invoke(cli, ["query", "--vault", vault, "--hop", "9", "x"])
    assert r.exit_code != 0
    r = runner.invoke(cli, ["stats", "--vault", vault])
    assert r.exit_code == 0 and '"notes": 8' in r.output
    r = runner.invoke(cli, ["analyze", "--vault", vault, "--json"])
    assert r.exit_code == 0 and '"orphans"' in r.output


def test_cli_requires_a_build(tmp_path: Path) -> None:
    r = CliRunner().invoke(cli, ["stats", "--vault", str(tmp_path)])
    assert r.exit_code != 0 and "run `vaultkg build` first" in r.output


def test_cli_snapshot_list_and_diff(vault: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(cli, ["build", "--vault", str(vault), "--no-index"]).exit_code == 0
    for key in ("v1", "v2"):
        r = runner.invoke(cli, ["snapshot", "save", "--vault", str(vault), key, "--force"])
        assert r.exit_code == 0, r.output
    r = runner.invoke(cli, ["snapshot", "list", "--vault", str(vault)])
    assert r.exit_code == 0 and "v1" in r.output and "v2" in r.output
    r = runner.invoke(cli, ["snapshot", "diff", "--vault", str(vault), "v1", "v2"])
    assert r.exit_code == 0, r.output


def test_build_no_index_drops_a_stale_vector_index(built: VaultKG) -> None:
    # A graph-only rebuild must not leave the previous build's vectors behind:
    # query would seed from nodes the new graph may no longer have.
    vault = built.repo_root
    vectors = built.vectors_path
    built.close()
    assert vectors.exists()
    r = CliRunner().invoke(cli, ["build", "--vault", str(vault), "--no-index"])
    assert r.exit_code == 0, r.output
    assert not vectors.exists()
    assert "removed the stale vector index" in r.output


def test_query_and_pack_without_an_index_say_so(vault: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(cli, ["build", "--vault", str(vault), "--no-index"]).exit_code == 0
    for cmd in ("query", "pack"):
        r = runner.invoke(cli, [cmd, "--vault", str(vault), "long contexts"])
        assert r.exit_code == 1
        assert "no vector index" in r.output


@pytest.mark.parametrize("missing", ["sentence_transformers", "torch.nn", "sqlite_vec"])
def test_query_without_the_semantic_extra_says_so(
    built: VaultKG, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    vault = str(built.repo_root)
    built.close()

    def no_extra(self: VaultKG, *args: object, **kwargs: object) -> None:
        raise ModuleNotFoundError(f"No module named {missing!r}", name=missing)

    monkeypatch.setattr(VaultKG, "query", no_extra)
    r = CliRunner().invoke(cli, ["query", "--vault", vault, "x"])
    assert r.exit_code == 1
    assert 'pip install "vault-kg[semantic]"' in r.output


def test_an_unrelated_missing_module_is_not_disguised(
    built: VaultKG, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = str(built.repo_root)
    built.close()

    def broken(self: VaultKG, *args: object, **kwargs: object) -> None:
        raise ModuleNotFoundError("No module named 'yaml'", name="yaml")

    monkeypatch.setattr(VaultKG, "query", broken)
    r = CliRunner().invoke(cli, ["query", "--vault", vault, "x"])
    assert isinstance(r.exception, ModuleNotFoundError)


def test_build_without_the_semantic_extra_stops_before_building(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util  # noqa: PLC0415

    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a: None if name == "sentence_transformers" else real(name, *a),
    )
    r = CliRunner().invoke(cli, ["build", "--vault", str(vault)])
    assert r.exit_code == 2
    assert "missing sentence_transformers" in r.output and "--no-index" in r.output
    assert not (vault / ".vaultkg" / "graph.sqlite").exists()
