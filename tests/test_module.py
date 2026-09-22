"""VaultKG end to end: build, health report, query and pack with a stub embedder."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from tests.conftest import HashEmbedder
from vaultkg.cli import cli
from vaultkg.module import VaultKG

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
