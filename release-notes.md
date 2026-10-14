# Release Notes -- v0.3.0

> Released: 2026-10-14

This release lets a vault remember what to leave out. Build excludes now live
in the vault, in `.vaultkg/config.yaml`, and every way of building or serving
the graph reads them: the `vaultkg` CLI, the MCP server, `viz3d` and the
KGRAG adapter. A private folder listed there stays out of the graph no matter
which tool builds it.

## What changed

**Persistent build config.** Create `<vault>/.vaultkg/config.yaml` with an
`exclude` list of folder names or globs, the same values `--exclude` takes.
`VaultKG` reads it when it is constructed, so a plain `vaultkg build` uses
it with no flags. `--exclude` still works and adds to the stored list for
that one build. A file that is not a mapping, has an unknown key, or has a
malformed list is an error rather than being silently ignored.

**Why it matters.** VaultKG does not read `.gitignore`. Before this release,
excludes existed only as command-line flags, so a build run without them
indexed every folder, including gitignored ones. In a real vault that put a
folder of private notes into the graph, and the MCP server then served them.
Keeping the list in the vault closes that gap for every entry point at once.

**Current fleet dependencies.** VaultKG now requires kgmodule-utils 0.26.0
and, for the 3-D views, quiltwright 0.16.0.

## Upgrading

```bash
uv tool install --force "vault-kg[semantic]==0.3.0"   # or: pip install -U vault-kg
```

Nothing changes until you add a config file; existing `--exclude` flags keep
working. To make your excludes permanent:

```yaml
# <vault>/.vaultkg/config.yaml
exclude:
  - templates
  - _inbox
```

The file is safe to commit; only the `.sqlite` files in `.vaultkg/` need
ignoring. Rebuild once after adding it.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
