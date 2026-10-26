# MCP server

`vaultkg mcp` serves one built vault to any MCP client: Claude Code, Cursor,
GitHub Copilot or Claude Desktop. `vaultkg-mcp` is the same command under its
older name. Build the vault first; the server doesn't build it, and refuses to
start a session if `<vault>/.vaultkg/graph.sqlite` doesn't exist.

The server is built on the fleet's shared base, `kg_utils.mcp`, so its first
five tools have the same names and arguments as every other fleet KG server.

## Configure a client

Add the server to the client's MCP configuration, such as `.mcp.json`:

```json
{
  "mcpServers": {
    "vaultkg": {
      "command": "vaultkg",
      "args": ["mcp", "--repo", "/path/to/vault"]
    }
  }
}
```

| Option | Meaning |
|---|---|
| `--repo DIRECTORY` | Vault root. Default `.`. `vaultkg-mcp` also takes `--vault` |
| `--db PATH` | Graph database. Default `<vault>/.vaultkg/graph.sqlite` |
| `--vectors PATH` | Vector index. Default `<vault>/.vaultkg/vectors.sqlite` |
| `--model NAME` | Embedding model. Default the one the vault was built with |
| `--transport [stdio\|streamable-http]` | MCP transport. Default `stdio` |
| `--host`, `--port` | Bind address for `streamable-http`. Default `127.0.0.1:8765` |
| `--manifest` | Print the tools as JSON and exit, without opening the graph |

## Tools

| Tool | Returns |
|---|---|
| `stats()` | Nodes and edges by kind and relation (the fleet stats shape), plus note, heading, tag and unresolved-link counts |
| `query(q, k, hop, max_nodes, rels)` | Semantic hits on notes and sections, expanded along their links |
| `pack(q, k, hop, max_nodes, rels)` | The same search with each note's or section's text, as Markdown |
| `get_node(node_id)` | One node and its metadata: title, tags, aliases, dates |
| `neighbors(node_id, rels, direction, limit)` | A node's edges in either direction and the nodes at their far ends |
| `note_links(node_id, direction, rel, limit)` | Outgoing links, or with `direction="in"` backlinks, including links to the note's sections |
| `analyze_vault()` | The [graph-health report](health.md) |
| `snapshot_list(limit)` | Saved snapshots, newest first |
| `snapshot_show(key)` | One snapshot; `key="latest"` for the newest |
| `snapshot_diff(key_a, key_b)` | The change between two snapshots |

`query` and `pack` need the `semantic` extra and a build with the
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

The server opens the graph when a session starts and closes it when the
session ends. Before vault-kg's port to `kg_utils.mcp`, `stats`, `query` and
`pack` were `graph_stats`, `query_vault` and `pack_vault`.
