"""Every ``vaultkg`` command and MCP tool has to appear on the documentation site.

connectome_kg 0.5.0 shipped three commands with nothing about them on its
site: the README had them, the pages did not, and Pages deployed green
because a missing page is not a build error. ``mkdocs build --strict`` checks
links between pages that exist, not pages that should. This test is the
check copied from connectome_kg for that gap.

The rule is deliberately weak -- the name has to appear somewhere in
``docs/`` -- because a strong one (every option, every example) would be
guesswork about what a page should say. A name that appears nowhere is a
command the site does not admit exists.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
import pytest

from vaultkg import mcp_server
from vaultkg.cli import cli

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
MKDOCS = ROOT / "mkdocs.yml"


def _pages() -> list[Path]:
    """Every Markdown page mkdocs renders, API reference stubs included."""
    return sorted(DOCS.rglob("*.md"))


def _commands(group: click.Group, prefix: str) -> list[str]:
    """Full command names, subcommands of a group included (``vaultkg snapshot save``)."""
    names: list[str] = []
    for name, cmd in sorted(group.commands.items()):
        names.append(f"{prefix} {name}")
        if isinstance(cmd, click.Group):
            names.extend(_commands(cmd, f"{prefix} {name}"))
    return names


@pytest.fixture(scope="module")
def site_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in _pages())


def test_there_are_commands_and_tools_to_check() -> None:
    """Guard the guard: an empty registry would make every assertion below pass."""
    assert len(_commands(cli, "vaultkg")) > 10
    assert len(asyncio.run(mcp_server.mcp.list_tools())) >= 9


def test_every_command_appears_on_the_site(site_text: str) -> None:
    missing = [name for name in _commands(cli, "vaultkg") if name not in site_text]
    assert not missing, (
        f"not documented anywhere in docs/: {', '.join(missing)}. Add them to a page "
        "listed in mkdocs.yml's nav, or the site will not admit the commands exist."
    )


def test_every_mcp_tool_appears_on_the_site(site_text: str) -> None:
    tools = [t.name for t in asyncio.run(mcp_server.mcp.list_tools())]
    missing = [name for name in tools if f"`{name}(" not in site_text]
    assert not missing, f"MCP tools not documented in docs/: {', '.join(missing)}"


def test_every_page_is_in_the_nav() -> None:
    """An unreferenced page builds but is reachable only by guessing its URL.

    Matched as text rather than parsed as YAML: a nav entry is
    ``- Title: path.md``, so the path appearing verbatim tells a listed page
    from an orphaned one.
    """
    nav = MKDOCS.read_text(encoding="utf-8").split("nav:", 1)[-1]
    orphans = [
        path.relative_to(DOCS).as_posix()
        for path in _pages()
        if path.relative_to(DOCS).as_posix() not in nav
    ]
    assert not orphans, f"not in mkdocs.yml nav: {', '.join(orphans)}"


def test_every_module_has_an_api_page() -> None:
    """A new public module with no API page is documented nowhere on the site."""
    documented = {p.stem for p in (DOCS / "api").glob("*.md")}
    # The CLI, MCP server and Qt window have their own pages; theme and
    # snapshots are configuration the pages describe in prose.
    prose_only = {"__init__", "cli", "mcp_server", "viz3d", "theme", "snapshots"}
    modules = {p.stem for p in (ROOT / "src" / "vaultkg").glob("*.py")} - prose_only
    assert modules == documented, (
        f"api pages missing for: {sorted(modules - documented)}; "
        f"api pages for no module: {sorted(documented - modules)}"
    )
