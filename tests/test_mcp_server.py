"""The MCP server, driven through ``mcp.shared.memory``'s in-process transport.

Every tool is called over the real protocol against a small built vault, not
by calling the underlying ``VaultKG`` method, and the lifespan hook is
checked to close the graph when the server stops (FLEET_STANDARDS, resource
cleanup).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult

from tests.conftest import HashEmbedder
from vaultkg import mcp_server
from vaultkg.module import VaultKG
from vaultkg.snapshots import SnapshotManager

pytestmark = pytest.mark.anyio

RETRIEVAL = "note:wiki/concepts/Retrieval.md"
LOST = "note:wiki/sources/Lost in the Middle.md"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def built(vault: Path) -> VaultKG:
    kg = VaultKG(vault)
    kg._embedder = HashEmbedder()
    kg.build(wipe=True)
    return kg


@asynccontextmanager
async def _session(kg: VaultKG) -> AsyncIterator[ClientSession]:
    mcp_server._kg = kg
    mcp_server._snapshot_mgr = SnapshotManager(
        kg.repo_root / VaultKG._default_dir / "snapshots", db_path=kg.db_path
    )
    try:
        async with create_connected_server_and_client_session(mcp_server.mcp) as session:
            yield session
    finally:
        mcp_server._kg = None
        mcp_server._snapshot_mgr = None


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


async def test_every_tool_is_listed(built: VaultKG) -> None:
    async with _session(built) as s:
        names = {t.name for t in (await s.list_tools()).tools}
    assert names == {
        "graph_stats",
        "query_vault",
        "pack_vault",
        "get_node",
        "note_links",
        "analyze_vault",
        "snapshot_list",
        "snapshot_show",
        "snapshot_diff",
    }


async def test_graph_stats(built: VaultKG) -> None:
    async with _session(built) as s:
        stats = json.loads(await _call(s, "graph_stats"))
    assert stats["notes"] == 8
    assert stats["unresolved"] == 2
    assert "docstring_coverage" not in stats


async def test_query_and_pack(built: VaultKG) -> None:
    async with _session(built) as s:
        res = json.loads(await _call(s, "query_vault", q="models ignore the middle", k=2))
        pack = await _call(s, "pack_vault", q="models ignore the middle", k=2, hop=0)
    assert LOST in [n["id"] for n in res["nodes"]]
    assert "Models ignore the middle" in pack


async def test_get_node_by_id_and_by_path(built: VaultKG) -> None:
    async with _session(built) as s:
        by_id = json.loads(await _call(s, "get_node", node_id=RETRIEVAL))
        by_path = json.loads(await _call(s, "get_node", node_id="`wiki/concepts/Retrieval`"))
        missing = json.loads(await _call(s, "get_node", node_id="no/such/note.md"))
    assert by_id["id"] == by_path["id"] == RETRIEVAL
    assert by_id["metadata"]["aliases"] == ["RAG"]
    assert missing is None


async def test_note_links_out_and_backlinks(built: VaultKG) -> None:
    async with _session(built) as s:
        out = json.loads(await _call(s, "note_links", node_id=RETRIEVAL, rel="extends"))
        back = json.loads(await _call(s, "note_links", node_id=LOST, direction="in"))
    assert [(r["rel"], r["node"]) for r in out] == [("EXTENDS", "note:wiki/concepts/Search.md")]
    assert any(r["rel"] == "SUPPORTS" for r in back)


async def test_analyze_vault(built: VaultKG) -> None:
    async with _session(built) as s:
        report = await _call(s, "analyze_vault")
    assert report.startswith("# VaultKG Analysis")


async def test_snapshot_tools(built: VaultKG) -> None:
    mgr = SnapshotManager(
        built.repo_root / VaultKG._default_dir / "snapshots", db_path=built.db_path
    )
    for key in ("v0.1.0", "v0.1.1"):
        mgr.save_snapshot(mgr.capture(graph_stats_dict=built.stats(), key=key), force=True)
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
        ("query_vault", {"q": "x", "k": 0}, "k must be between"),
        ("query_vault", {"q": "x", "hop": 6}, "hop must be between"),
        ("query_vault", {"q": "   "}, "q must not be empty"),
        ("pack_vault", {"q": "x", "max_nodes": 501}, "max_nodes must be between"),
        ("get_node", {"node_id": " "}, "node_id must not be empty"),
        ("get_node", {"node_id": "x" * 501}, "at most 500"),
        ("note_links", {"node_id": RETRIEVAL, "direction": "up"}, "direction must be"),
        ("note_links", {"node_id": RETRIEVAL, "limit": 0}, "limit must be between"),
        ("snapshot_list", {"limit": 501}, "limit must be between"),
        ("snapshot_show", {"key": "../../etc/passwd"}, "invalid snapshot key"),
        ("snapshot_diff", {"key_a": "a/b", "key_b": "v1"}, "invalid snapshot key"),
    ],
)
async def test_bad_arguments_are_rejected(
    built: VaultKG, tool: str, args: dict[str, object], message: str
) -> None:
    async with _session(built) as s:
        assert message in await _error(s, tool, **args)


async def test_lifespan_closes_kg_on_shutdown(built: VaultKG) -> None:
    async with _session(built) as s:
        await _call(s, "graph_stats")
    # The server task has unwound by the time the block exits, so the
    # lifespan's `finally: kg.close()` has already run.
    assert built._store is not None
    assert built._store._con is None


async def test_lifespan_is_a_noop_without_a_kg() -> None:
    assert mcp_server._kg is None
    async with create_connected_server_and_client_session(mcp_server.mcp):
        pass


async def test_tools_refuse_before_main_sets_the_kg() -> None:
    async with create_connected_server_and_client_session(mcp_server.mcp) as s:
        assert "vaultkg-mcp --vault" in await _error(s, "graph_stats")
        assert "vaultkg-mcp --vault" in await _error(s, "snapshot_list")


def test_parse_args_accepts_repo_alias() -> None:
    args = mcp_server._parse_args(["--repo", "/tmp/v", "--transport", "sse"])
    assert (args.vault, args.transport, args.db) == ("/tmp/v", "sse", None)


def test_main_opens_the_vault(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[str] = []
    monkeypatch.setattr(mcp_server.mcp, "run", lambda transport: ran.append(transport))
    try:
        mcp_server.main(["--vault", str(vault)])
        assert ran == ["stdio"]
        assert mcp_server._kg is not None and mcp_server._kg.repo_root == vault.resolve()
        assert mcp_server._snapshot_mgr is not None
    finally:
        mcp_server._kg = None
        mcp_server._snapshot_mgr = None
