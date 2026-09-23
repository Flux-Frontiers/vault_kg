# MCP server

`vaultkg-mcp` serves one built vault to any MCP client: Claude Code, Cursor,
GitHub Copilot or Claude Desktop. Build the vault first; the server doesn't
build it, and exits with an error if `<vault>/.vaultkg/graph.sqlite` doesn't
exist.

## Configure a client

Add the server to the client's MCP configuration, such as `.mcp.json`:

```json
{
  "mcpServers": {
    "vaultkg": {
      "command": "vaultkg-mcp",
      "args": ["--vault", "/path/to/vault"]
    }
  }
}
```

| Option | Meaning |
|---|---|
| `--vault DIRECTORY` | Vault root. Default `.`; `--repo` is an alias |
| `--db PATH` | Graph database. Default `<vault>/.vaultkg/graph.sqlite` |
| `--transport [stdio\|sse]` | MCP transport. Default `stdio` |

## Tools

| Tool | Returns |
|---|---|
| `graph_stats()` | Note, heading, tag and unresolved-link counts, and nodes and edges by kind |
| `query_vault(q, k, hop)` | Semantic hits on notes and sections, expanded along their links, as JSON |
| `pack_vault(q, k, hop, max_nodes)` | The same search with each note's or section's text, as Markdown |
| `get_node(node_id)` | One node and its metadata: title, tags, aliases, dates |
| `note_links(node_id, direction, rel, limit)` | Outgoing links, or with `direction="in"` backlinks, including links to the note's sections |
| `analyze_vault()` | The [graph-health report](health.md) |
| `snapshot_list(limit)` | Saved snapshots, newest first |
| `snapshot_show(key)` | One snapshot; `key="latest"` for the newest |
| `snapshot_diff(key_a, key_b)` | The change between two snapshots |

`query_vault` and `pack_vault` need the `semantic` extra and a build with the
vector index; without one they return an error saying so.

A `node_id` is a node id or a note's vault path, as on the command line.
`note_links` returns, for each link, the relation, the node at the other end,
the evidence (source line numbers and aliases), and `via`, the node the link
lands on, which for a backlink may be one of the note's sections.

## Argument bounds

Arguments are checked before they reach the graph. Out-of-range values are
rejected with a message naming the range, never clamped.

| Argument | Allowed |
|---|---|
| `k` | 1-100 |
| `hop` | 0-5 |
| `max_nodes`, `limit` | 1-500 |
| `q` | 1-2000 characters |
| `node_id` | 1-500 characters |
| snapshot keys | a tag or timestamp; never a path |

The server closes the graph when it stops, on either transport.
