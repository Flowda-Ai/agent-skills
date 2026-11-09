# flowda Agent Skills

Agent Skills that teach a coding agent to use the **flowda developer API**: fetch a
page, search the web, enumerate a site, run a published extraction template, and
monitor a page for changes. Every capability is a `flowda_*` MCP tool served by the
hosted MCP gateway at `https://mcp.flowda.ai/mcp` (Streamable HTTP); the skills tell
the model which tool to use, in what order, what it costs, and what goes wrong.

- **6 skills** — one router (`flowda`) plus five capability skills, installable on their own.
- **20 MCP tools** — `flowda_account`, `flowda_regions`, the two search dictionaries,
  `flowda_extract`, `flowda_template`, `flowda_templates_list`, `flowda_templates_get`,
  `flowda_search`, `flowda_map`, and the ten `flowda_watch_*` tools.
- **Hosted, no local server** — the MCP endpoint is configured for you by the plugin;
  you only supply an API key.

## Quick start (30 seconds)

1. Create an API key in the flowda console. It looks like `flw_<env>_<key_id>_<secret>`
   and carries per-capability scopes (`extract`, `search`, `map`, `watch`). There is no
   anonymous tier and no OAuth.
2. Export it in the shell that launches your client — the Claude Code plugin expands
   `${FLOWDA_API_KEY:-}` into the MCP `Authorization` header:

   ```bash
   export FLOWDA_API_KEY="flw_live_..."      # PowerShell: $env:FLOWDA_API_KEY = "flw_live_..."
   ```

3. Install the Claude Code plugin and restart Claude Code:

   ```bash
   claude plugin marketplace add Flowda-Ai/agent-skills
   claude plugin install flowda@flowda
   ```

4. Ask something:

   - "Fetch https://example.com and summarize it." → runs `flowda_extract`
   - "What are my flowda scopes?" → runs `flowda_account`

## Install matrix

| Client | What you get | How |
| --- | --- | --- |
| Claude Code | 6 skills + hosted MCP server | `claude plugin marketplace add Flowda-Ai/agent-skills` then `claude plugin install flowda@flowda` |
| Cursor (plugin) | 6 skills + hosted MCP server | import this repository in **Customize → Plugins → Add from GitHub Repository**, then set the `FLOWDA_API_KEY` plugin variable |
| Claude Code (MCP only) | hosted MCP server | `claude mcp add --transport http flowda https://mcp.flowda.ai/mcp --header "Authorization: Bearer flw_..."` |
| Cursor, Cline, Continue (MCP only) | hosted MCP server | the JSON block below in the client's MCP config |
| Codex CLI | hosted MCP server | `codex mcp add flowda --url https://mcp.flowda.ai/mcp --bearer-token-env-var FLOWDA_API_KEY` |
| Any Agent Skills client | 6 skills, no MCP server | `npx skills add Flowda-Ai/agent-skills -a <agent>` |

The generic skills install copies or links the skill directories only; the skills
still need the hosted MCP server to execute tools. See [docs/install.md](docs/install.md)
for per-client detail, the local stdio fallback and troubleshooting.

**For agents:** [llms.txt](llms.txt) is the repository index and
[docs/agent-onboarding.md](docs/agent-onboarding.md) is the five-step setup an agent
can follow on its own (get a key, install, connect MCP, verify with
`flowda_account`, troubleshoot).

Cursor / Cline / Continue (JSON):

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

Some clients name the transport `http`. Only Streamable HTTP is supported; the old
SSE transport is not.

Codex reads the key from the environment variable named by
`--bearer-token-env-var` in the shell that starts Codex, so export
`FLOWDA_API_KEY` (or use `codex mcp get flowda` to check the registration).

## Authentication

The skills themselves never carry a credential. The API key is configured on the
**MCP connection**, which is the only layer that talks to flowda — for the Claude
Code plugin that is the `FLOWDA_API_KEY` environment variable expanded by
`.mcp.json`; the other clients put it in their own `mcpServers` headers. See
[docs/install.md §0](docs/install.md#0-how-the-key-reaches-flowda-read-this-first)
for the per-client table, the rotation steps and the "never commit a key" rules.

The MCP layer forwards your credential to the API, which decides auth, scopes, rate
limits and quota. The credential must be an API key that starts with `flw_`; a
console **session token is rejected** by the gateway. Tools are filtered per key:
a key without the `watch` scope does not see the watch tools, and calling one anyway
returns 403 with code `12015` and `data.required_scope` naming the missing scope.
`flowda_account` reports which scopes a key carries.

| Scope | Unlocks |
| --- | --- |
| `extract` | `flowda_extract`, `flowda_template`, `flowda_templates_list`, `flowda_templates_get` |
| `search` | `flowda_search` |
| `map` | `flowda_map` |
| `watch` | the ten `flowda_watch_*` tools |

## Skills

| Skill | Use it when |
| --- | --- |
| `flowda` | Routing. Which capability fits, what it costs, how errors and scopes work, which dictionaries to use. Start here. |
| `flowda-extract` | Read one page as markdown, raw HTML, clean HTML or links. |
| `flowda-search` | Search the web (billed per result), optionally extracting each result inline. |
| `flowda-map` | List the URLs of a site, with sitemap, domain-filter and limit controls. |
| `flowda-template` | Run one of the six published Amazon / Walmart extraction templates: list, get, run. |
| `flowda-watch` | Monitor a page on a schedule, receive webhook callbacks or poll, read diffs and check history. |

## Evals

```bash
claude plugin eval . --trust-plugin --ablation none --mocks off
```

The suite lives in `evals/` (one directory per case, `case.yaml` + LLM grader) and
covers routing, platform-failure reporting, no-retry-after-timeout, monitoring
confirmation, search dictionaries, `request_id` quoting, the template flow and map
routing. Cases need `FLOWDA_API_KEY` and `--allow-real-servers` when they call the
live MCP server; schema-only validation is possible with `--max-cost-usd 0`.
Results land in `evals/results/`. Details and the full command in
[evals/README.md](evals/README.md).

## Repository layout and maintenance

```
skills/            six self-contained Agent Skills
.claude-plugin/    Claude Code plugin and marketplace manifests
.codex-plugin/     Codex plugin manifest
.cursor-plugin/    Cursor plugin and marketplace manifests
.mcp.json          hosted MCP server configuration for Claude Code
mcp.json           the same server for clients that discover mcp.json at the root
llms.txt           agent-facing index of the repository
evals/             behaviour evals (case.yaml per case)
spec/, scripts/    API contract snapshot and generators — not installed as skills
docs/              install, agent onboarding and maintenance guides
```

Contract facts (endpoints, fields, limits, error codes, tool names, budgets) come from
`spec/openapi.snapshot.json` and `scripts/tool_map.py`; the field tables under
`skills/flowda/references/params/` are generated. Read [docs/authoring.md](docs/authoring.md)
before changing a skill, a manifest or a generated file — it lists the sources of
truth, the canonical rules block and the release gate (`scripts/validate_skills.py`
plus `claude plugin validate . --strict`).

License: TBD — this repository ships no LICENSE file yet.
