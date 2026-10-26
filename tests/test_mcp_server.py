"""The MCP server on the fleet's shared base, ``kg_utils.mcp``.

Driven through ``mcp.shared.memory``'s in-process transport: every tool is
called over the real protocol against a small built vault, not by calling the
underlying ``VaultKG`` method. The server opens its own ``VaultKG`` per
session; these tests give it the hash embedder so no model is downloaded.

Then the surface step 2 of kgrag_priv's MCP centralization plan promises: the
five canonical tools first, under the names every fleet server shares, then
VaultKG's extras; ``stats`` in the fleet shape; the manifest answers without a
graph; other ``vaultkg`` commands do not import ``mcp``; an unbuilt vault is
refused; ``vaultkg-mcp --vault`` still works; and a real stdio subprocess
serves.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
import pytest
from click.testing import CliRunner
from kg_utils.mcp import CANONICAL_TOOLS, manifest
from kg_utils.stats import stats_problems
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult

import vaultkg
from tests.conftest import HashEmbedder
from vaultkg import mcp_server
from vaultkg.cli import cli
from vaultkg.module import VaultKG
from vaultkg.snapshots import SnapshotManager

RETRIEVAL = "note:wiki/concepts/Retrieval.md"
LOST = "note:wiki/sources/Lost in the Middle.md"
_SRC = str(Path(vaultkg.__file__).resolve().parents[1])


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _HashVaultKG(VaultKG):
    """VaultKG with the hash embedder, as the server opens it in these tests."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._embedder = HashEmbedder()


@pytest.fixture
def built(vault: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    kg = VaultKG(vault)
    kg._embedder = HashEmbedder()
    kg.build(wipe=True)
    kg.close()
    monkeypatch.setattr(mcp_server, "VaultKG", _HashVaultKG)
    return vault


@asynccontextmanager
async def _session(vault: Path) -> AsyncIterator[ClientSession]:
    async with create_connected_server_and_client_session(
        mcp_server.build_server(vault)
    ) as session:
        yield session


def _text(result: CallToolResult) -> str:
    return "".join(c.text for c in result.content if hasattr(c, "text"))


async def _call(session: ClientSession, tool: str, **args: object) -> str:
    result = await session.call_tool(tool, args)
    assert not result.isError, _text(result)
    return _text(result)


async def _error(session: ClientSession, tool: str, **args: object) -> str:
    result = await session.call_tool(tool, args)
    assert result.isError
    return _text(result)


@pytest.mark.anyio
async def test_canonical_tools_then_the_extras(built: Path) -> None:
    async with _session(built) as s:
        names = [t.name for t in (await s.list_tools()).tools]
    assert names == [
        *CANONICAL_TOOLS,
        "note_links",
        "analyze_vault",
        "snapshot_list",
        "snapshot_show",
        "snapshot_diff",
    ]


@pytest.mark.anyio
async def test_stats(built: Path) -> None:
    async with _session(built) as s:
        stats = json.loads(await _call(s, "stats"))
    assert stats_problems(stats) == []
    assert stats["kind"] == "vault"
    assert stats["notes"] == 8
    assert stats["unresolved"] == 2
    assert "docstring_coverage" not in stats


@pytest.mark.anyio
async def test_query_and_pack(built: Path) -> None:
    async with _session(built) as s:
        res = json.loads(await _call(s, "query", q="models ignore the middle", k=2))
        pack = await _call(s, "pack", q="models ignore the middle", k=2, hop=0)
    assert LOST in [n["id"] for n in res["nodes"]]
    assert "Models ignore the middle" in pack


@pytest.mark.anyio
async def test_get_node_by_id_and_by_path(built: Path) -> None:
    async with _session(built) as s:
        by_id = json.loads(await _call(s, "get_node", node_id=RETRIEVAL))
        by_path = json.loads(await _call(s, "get_node", node_id="`wiki/concepts/Retrieval`"))
        missing = await _error(s, "get_node", node_id="no/such/note.md")
    assert by_id["id"] == by_path["id"] == RETRIEVAL
    assert by_id["metadata"]["aliases"] == ["RAG"]
    assert "no node with id" in missing


@pytest.mark.anyio
async def test_neighbors_by_path(built: Path) -> None:
    async with _session(built) as s:
        near = json.loads(
            await _call(s, "neighbors", node_id="wiki/concepts/Retrieval", direction="out")
        )
    assert near["node"]["id"] == RETRIEVAL
    assert "note:wiki/concepts/Search.md" in [n["id"] for n in near["nodes"]]


@pytest.mark.anyio
async def test_note_links_out_and_backlinks(built: Path) -> None:
    async with _session(built) as s:
        out = json.loads(await _call(s, "note_links", node_id=RETRIEVAL, rel="extends"))
        back = json.loads(await _call(s, "note_links", node_id=LOST, direction="in"))
    assert [(r["rel"], r["node"]) for r in out] == [("EXTENDS", "note:wiki/concepts/Search.md")]
    assert any(r["rel"] == "SUPPORTS" for r in back)


@pytest.mark.anyio
async def test_analyze_vault(built: Path) -> None:
    async with _session(built) as s:
        report = await _call(s, "analyze_vault")
    assert report.startswith("# VaultKG Analysis")
    # The counts tables read the stats shape; on the old keys they were empty.
    assert "| note | 8 |" in report


@pytest.mark.anyio
async def test_snapshot_tools(built: Path) -> None:
    kg = VaultKG(built)
    mgr = SnapshotManager(kg.repo_root / VaultKG._default_dir / "snapshots", db_path=kg.db_path)
    for key in ("v0.1.0", "v0.1.1"):
        mgr.save_snapshot(mgr.capture(graph_stats_dict=kg.stats(), key=key), force=True)
    kg.close()
    async with _session(built) as s:
        listed = json.loads(await _call(s, "snapshot_list", limit=5))
        latest = json.loads(await _call(s, "snapshot_show"))
        diff = json.loads(await _call(s, "snapshot_diff", key_a="v0.1.0", key_b="v0.1.1"))
        none = json.loads(await _call(s, "snapshot_show", key="v9.9.9"))
    assert {e["key"] for e in listed} == {"v0.1.0", "v0.1.1"}
    assert latest["key"] in {"v0.1.0", "v0.1.1"}
    assert diff
    assert none is None


@pytest.mark.parametrize(
    ("tool", "args", "message"),
    [
        ("query", {"q": "x", "k": 0}, "k must be between"),
        ("query", {"q": "x", "hop": 6}, "hop must be between"),
        ("query", {"q": "   "}, "q must not be empty"),
        ("pack", {"q": "x", "max_nodes": 501}, "max_nodes must be between"),
        ("get_node", {"node_id": " "}, "node_id must not be empty"),
        ("get_node", {"node_id": "x" * 501}, "at most 500"),
        ("note_links", {"node_id": RETRIEVAL, "direction": "up"}, "direction must be"),
        ("note_links", {"node_id": RETRIEVAL, "limit": 0}, "limit must be between"),
        ("neighbors", {"node_id": RETRIEVAL, "limit": 0}, "limit must be between"),
        ("snapshot_list", {"limit": 501}, "limit must be between"),
        ("snapshot_show", {"key": "../../etc/passwd"}, "invalid snapshot key"),
        ("snapshot_diff", {"key_a": "a/b", "key_b": "v1"}, "invalid snapshot key"),
    ],
)
@pytest.mark.anyio
async def test_bad_arguments_are_rejected(
    built: Path, tool: str, args: dict[str, object], message: str
) -> None:
    async with _session(built) as s:
        assert message in await _error(s, tool, **args)


@pytest.mark.anyio
async def test_the_session_opens_the_graph_and_closes_it(
    built: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[VaultKG] = []
    real_close = VaultKG.close

    def counting_close(self: VaultKG) -> None:
        closed.append(self)
        real_close(self)

    monkeypatch.setattr(VaultKG, "close", counting_close)
    async with _session(built) as s:
        await _call(s, "stats")
        assert closed == [], "the graph stays open for the whole session"
    assert len(closed) == 1
    assert closed[0]._store is not None and closed[0]._store._con is None


def test_an_unbuilt_vault_is_refused_not_served_empty(vault: Path) -> None:
    async def run() -> None:
        async with create_connected_server_and_client_session(mcp_server.build_server(vault)):
            pass

    with pytest.raises(BaseException) as info:
        anyio.run(run)
    assert "no graph at" in repr(info.value) or any(
        "no graph at" in str(e) for e in getattr(info.value, "exceptions", ())
    )
    assert not (vault / ".vaultkg" / "graph.sqlite").exists()


def test_manifest_answers_without_a_graph_and_creates_nothing(vault: Path) -> None:
    result = CliRunner().invoke(cli, ["mcp", "--repo", str(vault), "--manifest"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["canonical"] == list(CANONICAL_TOOLS)
    assert manifest(mcp_server.build_server(vault))["kind"] == "vault"
    assert not (vault / ".vaultkg").exists()


def test_vaultkg_mcp_takes_vault_for_repo(vault: Path) -> None:
    """``vaultkg-mcp --vault`` is the same command as ``vaultkg mcp --repo``."""
    via_cli = CliRunner().invoke(cli, ["mcp", "--repo", str(vault), "--manifest"]).output
    via_script = subprocess.run(
        [
            sys.executable,
            "-c",
            "from vaultkg.mcp_server import main; main()",
            "--vault",
            str(vault),
            "--manifest",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert json.loads(via_cli) == json.loads(via_script)


def test_sse_is_gone(vault: Path) -> None:
    result = CliRunner().invoke(
        cli, ["mcp", "--repo", str(vault), "--transport", "sse", "--manifest"]
    )
    assert result.exit_code == 2


def test_other_commands_do_not_import_mcp() -> None:
    out = subprocess.run(
        [sys.executable, "-c", "import sys, vaultkg.cli; print('mcp' in sys.modules)"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert out == "False"


def test_stdio_subprocess_serves(built: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from vaultkg.mcp_server import main; main()", "--vault", str(built)],
        env={**os.environ, "PYTHONPATH": _SRC},
    )

    async def run():
        with open(built / "stderr.log", "w", encoding="utf-8") as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as client:
                    init = await client.initialize()
                    tools = await client.list_tools()
                    stats = await client.call_tool("stats", {})
                    return init, tools, stats

    init, tools, stats = anyio.run(run)
    assert (init.serverInfo.name, init.serverInfo.version) == ("vaultkg", vaultkg.__version__)
    assert [t.name for t in tools.tools][: len(CANONICAL_TOOLS)] == list(CANONICAL_TOOLS)
    assert stats.structuredContent["notes"] == 8
