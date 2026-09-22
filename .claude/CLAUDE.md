# VaultKG project instructions

## Overview

VaultKG is a KGModule over Obsidian-style Markdown vaults. It subclasses
`kg_utils.pipeline.KGModule` and lets the shared SDK own storage, indexing,
query, pack and argument validation. The graph is parsed, never extracted by
a model: `parse.py` reads one note, `extractor.py` resolves links the way
Obsidian does, `analysis.py` computes graph health, `mcp_server.py` serves it.

Fleet-wide rules (dependency conventions, hooks, releases, temporal contract,
snapshots, MCP hardening) are in `kgrag_priv/docs/FLEET_STANDARDS.md`.
Cross-repo TODO items go in `kgrag_priv/FLEET_SWEEP_PLAN.md`, never here.

## Development workflow

```bash
env -u VIRTUAL_ENV -u POETRY_ACTIVE poetry install --with dev --all-extras --sync
env -u VIRTUAL_ENV -u POETRY_ACTIVE .venv/bin/pytest --cov
env -u VIRTUAL_ENV -u POETRY_ACTIVE .venv/bin/pre-commit run --all-files
```

Always unset `VIRTUAL_ENV` for repo commands; an inherited venv from another
fleet repo hijacks `poetry run` silently. Run pre-commit on all files before
any commit: the hook chain runs `ty` and the full suite with the coverage
floor.

`dockg` and `pycodekg` are global tools (`uv tool install`), not
dependencies. `.mcp.json` calls them from `PATH`.

## Rules for this module

- Node ids are stable: `note:<path>`, `heading:<path>#<slug>[~n]`,
  `tag:<folded tag>`, `attachment:<path>`, `missing:<folded target>`. Two
  builds of the same vault must produce the same graph.
- Validate external input once, in `VaultKG` (`node()`, `links()`), and let
  the `KGModule` base validate `query()`/`pack()`. The CLI and MCP server
  both go through those methods; never add a second check at a surface.
- Snapshots configure the base `SnapshotManager` (`package_name`,
  `_domain_metrics`, `metrics_ignore`, `dict_metric_deltas`); never override
  its save/load/capture methods.
- Temporal keys come from frontmatter `date`/`created` only, through
  `_note_dates()`. Never from file mtimes.
- Tests embed with `tests/conftest.py`'s `HashEmbedder`; no test may download
  a model.

## Code style

- `:param:` docstrings
- ruff for format and lint (line length 100), ty for types
- plain ASCII in prose, comments and docstrings: `--` not an em dash, `->`
  not an arrow glyph
