# Install and connect flowda

The pack ships two things that are installed separately:

- **Agent Skills** — six directories under `skills/`, plain `SKILL.md` + references.
  Any client that supports Agent Skills can read them; no runtime code.
- **MCP configuration** — the hosted flowda MCP server at
  `https://mcp.flowda.ai/mcp`. The skills assume its 20 `flowda_*` tools exist.

This guide covers every supported client, how to verify the connection, and what
each error means. If you are an AI agent rather than a person, read
[agent-onboarding.md](agent-onboarding.md): it is the same setup in a form you can
follow on your own.

## 0. How the key reaches flowda (read this first)

The pack has three separate pieces, and only one of them holds the key:

| Layer | What it is | Holds the key? |
| --- | --- | --- |
| Skill (`skills/*/SKILL.md`) | instructions for the model: which tool to call, when, what it costs, what goes wrong | **No.** Skills are public text and never contain a credential |
| MCP server (`https://mcp.flowda.ai/mcp`) | the connection that exposes the 20 `flowda_*` tools and calls `/v1` | Verifies it per request; does not store it |
| MCP client configuration (`.mcp.json`, `mcp.json`, Codex config, a shell environment variable) | where **you** put the key on your own machine | **Yes** — this is the only place the key lives |

So "using the skill" is two installs: the skill files, and an MCP connection that
carries `Authorization: Bearer flw_...`. A skill without that connection has no
tools to call; a connection without the skill still works, it just gives the model
no judgement about which tool to use or what it costs.

The key is never sent to the model. It stays in the HTTP header between your MCP
client and the gateway; the model only sees the tools and their results.

Where each client keeps it:

| Client | Where the key is configured | To rotate the key |
| --- | --- | --- |
| Claude Code + this plugin | environment variable `FLOWDA_API_KEY` in the shell that starts Claude Code; the plugin's `.mcp.json` expands it into the `Authorization` header | export the new value and restart Claude Code |
| Claude Code, direct MCP | inside the server entry created by `claude mcp add ... --header` | re-run `claude mcp add` (or edit the entry) with the new key |
| Cursor | `~/.cursor/mcp.json` → `headers`; `${env:FLOWDA_API_KEY}` interpolation is supported, so the literal key can stay out of the file | update the variable and restart Cursor |
| Cline | `~/.cline/data/settings/cline_mcp_settings.json` → `headers` (or `cline mcp add ... --header`); recent versions also support environment interpolation | edit the entry and restart the MCP server |
| Continue | its MCP config file, same `mcpServers` + `headers` shape | edit the entry and restart |
| Codex CLI | kept in the environment, referenced by `--bearer-token-env-var FLOWDA_API_KEY` | export the new value; no config edit |
| Local stdio | `FLOWDA_API_KEY` in the environment of the process | export the new value and restart |

Rules that save support tickets:

- **Never commit a key.** Do not put one in this repository, a README, a skill, a
  URL, or a chat message. The plugin path exists so the key can stay in the
  environment instead of a tracked file.
- **Launch the client from a shell that has the variable.** A GUI-launched app or a
  fresh terminal may not inherit it; export it in the profile that starts the app, then
  restart the app. With the plugin, an unset variable becomes `Authorization: Bearer `
  and the gateway answers 401 `12001`.
- **A console session token is not an MCP credential.** It does not start with `flw_`
  and the gateway rejects it on purpose (a session bypasses scopes in `/v1`).
- **A missing scope is not a bad key.** It is 403 `12015` with `data.required_scope`;
  fix the grant in the console, do not rotate the key.

## 1. Before you start

1. Create an API key in the flowda console. Key format:
   `flw_<env>_<key_id>_<secret>`. The key carries per-capability scopes:
   `extract` (extract, template, templates), `search`, `map`, `watch`. A key that
   lacks a scope still authenticates; the refused call returns 403 with code
   `12015` and `data.required_scope`.
2. There is **no anonymous tier and no OAuth**. The gateway accepts API keys only —
   a console session token (JWT) does not start with `flw_` and is rejected, so do
   not paste a session token into a client.
3. Export the key in the shell that launches your client. The Claude Code plugin
   expands `${FLOWDA_API_KEY:-}` into the `Authorization` header; the other clients
   use the key directly in their configuration.

   ```bash
   export FLOWDA_API_KEY="flw_live_..."        # bash / zsh
   ```

   ```powershell
   $env:FLOWDA_API_KEY = "flw_live_..."        # PowerShell
   ```

Facts about the hosted endpoint:

| Property | Value |
| --- | --- |
| URL | `https://mcp.flowda.ai/mcp` |
| Transport | Streamable HTTP (no SSE); `GET`/`DELETE` answer 405 |
| Auth | `Authorization: Bearer flw_...`; no credential answers 401 + `WWW-Authenticate: Bearer realm="flowda"` |
| Request size | 256 KiB (the nginx front end allows 1 MiB; the gateway enforces 256 KiB) |
| Longest call | 130 s budget for extract / template / map, 60 s for search; the proxy waits 180 s |
| Streamed progress | supported when the client sends a progress token |

## 2. Claude Code — plugin (skills + hosted MCP)

```bash
claude plugin marketplace add Flowda-Ai/agent-skills
claude plugin install flowda@flowda
```

Restart Claude Code after installing. The plugin registers the MCP server from
`.mcp.json` and loads all six skills from `skills/`. Because the manifest expands
`${FLOWDA_API_KEY:-}`, the shell that starts Claude Code must have the variable set;
if it is empty the client sends `Authorization: Bearer ` and the gateway answers 401.

Check the install:

```bash
claude plugin list
claude mcp list
```

Then ask "What are my flowda scopes?" — it calls `flowda_account`.

## 3. Claude Code — MCP server without the plugin

```bash
claude mcp add --transport http flowda https://mcp.flowda.ai/mcp \
  --header "Authorization: Bearer $FLOWDA_API_KEY"
```

PowerShell:

```powershell
claude mcp add --transport http flowda https://mcp.flowda.ai/mcp `
  --header "Authorization: Bearer $env:FLOWDA_API_KEY"
```

Inspect or remove it with `claude mcp get flowda` / `claude mcp remove flowda`.
The header is stored with the server definition, so changing the environment
variable later does not change the stored credential — re-add the server.

## 4. Cursor

### 4.1 Cursor plugin (skills + MCP in one)

The repository is a Cursor plugin: `.cursor-plugin/plugin.json` is the manifest and
`.cursor-plugin/marketplace.json` lets Cursor import the repository as a marketplace.

1. **Customize → Plugins → Add from GitHub Repository**, enter
   `https://github.com/Flowda-Ai/agent-skills`, then install the `flowda` plugin.
2. Set the plugin variable **`FLOWDA_API_KEY`** in **Customize → Plugins → flowda →
   Configure**. The plugin's `mcp.json` sends it as
   `Authorization: Bearer ${FLOWDA_API_KEY}`.
3. Restart Cursor, then confirm `flowda` appears under MCP and that the six skills
   are listed.

The plugin's root `mcp.json` is the Cursor-readable copy of the same server that
`.mcp.json` configures for Claude Code; the key is a plugin variable here and an
environment variable there.

### 4.2 Cursor / Cline / Continue without the plugin (MCP only)

Add this server object to the client's MCP configuration:

```json
{
  "mcpServers": {
    "flowda": {
      "type": "streamable-http",
      "url": "https://mcp.flowda.ai/mcp",
      "headers": { "Authorization": "Bearer flw_live_..." }
    }
  }
}
```

- **Cursor** — project config `.cursor/mcp.json`, or the equivalent user-level MCP
  settings; the same `mcpServers` shape.
- **Cline** — MCP Servers panel; paste the server object into its JSON settings.
- **Continue** — MCP servers are configured in its own config file with the same
  `mcpServers` shape.

Some clients call the transport `http` instead of `streamable-http`; both mean the
same thing. Only Streamable HTTP is supported — the old SSE transport is not.

## 5. Codex CLI

Register the hosted server once; the key stays in the environment, not in Codex's
configuration:

```bash
export FLOWDA_API_KEY="flw_live_..."
codex mcp add flowda --url https://mcp.flowda.ai/mcp --bearer-token-env-var FLOWDA_API_KEY
codex mcp list          # shows flowda / enabled / Bearer token
codex mcp get flowda    # shows the final registration
```

`--bearer-token-env-var` is read from the environment of the shell that starts
Codex, so export the variable in every new shell (or set it in your shell profile).
Run a smoke test:

```bash
codex exec --skip-git-repo-check --ephemeral \
  "Use flowda. Call flowda_account and show my scopes."
```

The repository also ships a Codex plugin manifest at `.codex-plugin/plugin.json`
(`"skills": "./skills"`) for Codex plugin marketplaces. It deliberately does not
embed an MCP server: Codex users register the server with `codex mcp add` as above,
and environment-variable expansion in a bundled `.mcp.json` is not verified for
Codex.

## 6. Skills without the MCP server

```bash
npx skills add Flowda-Ai/agent-skills
```

This installs the six skill directories into your client's skills location (add
`-l` to list them first, `-a <agents>` to target specific clients). The skills
document the tools but cannot execute them: point the same client at the hosted MCP
server with one of the sections above.

## 7. Local stdio fallback

The MCP gateway is a separate project (`flowda-mcp-service`) and can run locally over
stdio instead of the hosted endpoint. Build it, then register it with the client:

```powershell
go build -o bin/flowda-mcp.exe ./cmd/mcp
$env:FLOWDA_API_KEY = "flw_live_..."
$env:MCP_UPSTREAM_BASE_URL = "https://openapi.flowda.ai"
$env:MCP_TRANSPORT = "stdio"
.\bin\flowda-mcp.exe
```

Claude Code:

```powershell
claude mcp add --transport stdio flowda `
  --env FLOWDA_API_KEY=flw_live_... `
  --env MCP_UPSTREAM_BASE_URL=https://openapi.flowda.ai `
  -- C:\path\to\flowda-mcp.exe
```

Notes: `FLOWDA_API_KEY` is required for stdio and must start with `flw_` (the process
refuses to start otherwise); all logs go to stderr so stdout carries protocol frames
only. The tool surface and semantics are identical to the hosted endpoint.

## 8. Verify the connection

The cheapest end-to-end check is the account tool — it is free, read-only and works
while diagnosing a 403:

- Ask "What are my flowda scopes?" or call `flowda_account` with no arguments.
- In a direct JSON-RPC client, `tools/list` should return the `flowda_*` tools your
  key can use; `tools/call` with `{"name":"flowda_account","arguments":{}}` returns
  `auth_method`, `credential_source`, `scopes`, `scope_enforced`,
  `daily_credit_quota` and `key_id`.

If `auth_method` is not `api_key`, the client is sending something other than a key.

## 9. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| 401 — no credential (the gateway's own `{"error":"unauthorized"}`, or `/v1` code `12001` once an empty key is forwarded) | No usable credential reached the gateway — usually `FLOWDA_API_KEY` was unset when the client started, so the plugin sent `Authorization: Bearer ` | Export the key in the shell that launches the client, then restart it |
| 401, code `12014` (invalid api key) | Key is invalid, revoked or expired | Create a new key in the console and re-register |
| 403, code `12015` | The key is valid but lacks the endpoint's scope; `data.required_scope` names it | Add that scope to the key in the console; the gateway's scope cache refreshes within 300 s, so reconnect after a scope change |
| 429, code `13000` | Rate limit exceeded | Back off using the `Retry-After` response header; do not hammer the endpoint |
| 402, code `13002` | Daily credit quota exhausted | Wait for the next UTC day or ask for a higher quota; retrying now cannot succeed |
| 404, code `11004` on every `/v1` route | The developer surface is switched off (`jdata.enabled=false`); the uniform 404 is deliberate, not a wrong URL | Contact the operator; nothing in the client can fix it |
| No tools visible / tools missing | `tools/list` is filtered by the key's scopes; a key with `extract` does not see the watch tools | Call `flowda_account` to see the actual scopes, then add the missing scope |
| 503, `{"error":"mcp_disabled"}` | The gateway is disabled by the operator (`MCP_ENABLED=false`) | Try later or use another deployment |
| 413 | Request body over 256 KiB | Send fewer URLs / smaller arguments |
| 405 on `GET /mcp` | Expected — the endpoint is POST-only for Streamable HTTP | Use the client's MCP configuration, not a browser |
| A call timed out | There is no idempotency key: the call may already be billed | Do **not** retry a billed call; quote the `request_id` and check the console Logs |

Two failure modes are easy to misread:

- **HTTP 200 is not success.** A capability call can return HTTP 200, `code: 0`
  and `data.success: false` with a platform code and message. Treat that as a
  failure and report the platform code and `request_id`.
- **`request_id` is how support finds a call.** Every response carries one; the
  console Logs are keyed by it. Quote it in any report or support request instead
  of describing the call.
