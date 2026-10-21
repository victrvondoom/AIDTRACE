# Engineering Memory Vault

Kairos Agent Sandbox includes a human-authored engineering memory vault for coding agents. Dictated judgments are transcribed for review, then stored as procedural memories in a dedicated FalkorDB graph derived from the authenticated site. The graph has a separate namespace from operational supplier/evidence memory and is shared by agents configured for the same site. Point `FALKORDB_URL` at local FalkorDB for local persistence; durability across restarts follows the configured FalkorDB volume and backup policy. This is a separate graph in the configured database, not a separate database daemon or cloud microVM.

The authenticated `/agent-memory/engineering` API reads and writes the vault. Voice transcription uses the configured Groq Whisper service; audio is limited to 10 MB and is not saved by the transcription endpoint. The transcript must be reviewed and explicitly saved. Memory records preserve the complete text, content hash, author, tags, and capture time. Vault reads page through the complete graph; if the store cannot return a complete view, recall and export fail instead of returning a silent partial list. Complete export is bounded at 10,000 records.

## MCP client

The stdio MCP server is read-only. It exposes `engineering_memory_recall` and `engineering_memory_rules`. Recall returns only `VALID` judgments and pages through every matching result; stale or invalidated judgments remain visible in the authenticated UI with their status but are excluded from agent guidance. Coding agents cannot create or edit memories through MCP; add guidance in Kairos so a model cannot silently teach itself project policy.

Install `backend/requirements-mcp.txt` in a dedicated MCP virtual environment. Do not install its MCP SDK into the pinned Kairos API environment. Configure the MCP client with the path to `backend` as `cwd` and set:

```json
{
  "mcpServers": {
    "kairos-engineering-memory": {
      "command": "<mcp-venv-python>",
      "args": ["-m", "api.services.memory.engineering_mcp"],
      "cwd": "<path-to-kairos-main/backend>",
      "env": {
        "KAIROS_ENGINEERING_SITE": "<authenticated-site-id>",
        "FALKORDB_URL": "<approved-local-or-remote-falkordb-url>"
      }
    }
  }
}
```

Keep the FalkorDB URL in the MCP client's secret environment when possible. The site identifier is operator configuration and is never accepted as a tool argument. The MCP process derives the same isolated graph as the API.

## Rules export and limits

Use **Export agent rules + MCP** in Agent Sandbox to download an `AGENTS.md` with current active judgments and fail-closed recall instructions, plus a client configuration template. Place the generated rules file where the coding agent reads repository instructions and configure its MCP client. The generated rule asks the agent to stop with `ENGINEERING_MEMORY_UNAVAILABLE` if recall fails.

This makes missing memory explicit and reviewable. It cannot guarantee compliance by every third-party agent runtime, and no memory store can make an agent literally incapable of forgetting. The server and database must be reachable, and the generated `AGENTS.md` must be installed in the target repository. MCP recall has a per-call result limit; the exported rules direct the coding agent to query before work and stop when the vault is unavailable.
