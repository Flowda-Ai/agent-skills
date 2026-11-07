# Evals

Behaviour evals for the flowda skill pack, in Claude Code's native plugin eval
format. One directory per case:

```
evals/<case-name>/case.yaml
```

The target is the repository root (the plugin); the default eval directory is
`evals/`, so no flag is needed when running from the root.

## Run

```bash
export FLOWDA_API_KEY="flw_live_..."    # optional, see below
claude plugin eval . --trust-plugin --ablation none --mocks off
```

Useful flags:

| Flag | Purpose |
| --- | --- |
| `--case <glob>` | Run only matching cases, e.g. `--case 'timeout-*'` |
| `--runs 1` | One run per case instead of the default three (cheaper) |
| `--model <model>` | Override the model under test |
| `--json <path>` / `--report <path>` | Machine-readable result / HTML report |
| `--max-cost-usd 0` | Validate the suite without launching any model run |

`--trust-plugin` skips the first-run trust prompt (only use it on this repository).
`--ablation none` runs the plugin arm only; without it the CLI adds a no-plugin
baseline arm and roughly doubles the number of runs.

## Schema-only validation

```bash
claude plugin eval . --trust-plugin --max-cost-usd 0 --mocks off
```

This loads and validates every `case.yaml`, then stops at the cost ceiling before
any agent run, so it costs nothing. A malformed file is named explicitly, for
example:

```
✗ evals/<case>/case.yaml: invalid case.yaml: ... 
```

The cost-ceiling abort itself prints `⚠ cost ceiling $0 hit` and exits 2 (the CLI
documents the ceiling abort as exit 2) — that is the expected result of this check,
not a case-file error.

## Real MCP tools

The hosted MCP server is configured in `.mcp.json` at the repository root. Cases
that need live tool calls require:

1. `FLOWDA_API_KEY` exported in the shell running the eval, and
2. the plugin's real MCP server actually started. With the default
   `--mocks record` the real server is not started unless you add
   `--allow-real-servers`; `--mocks off` starts it, and where a run would otherwise
   stop for permission on the `mcp__*` tools, grant them with `--allow-tools`.

The shipped cases are written so the skill guidance plus the prompt is enough to
answer (they embed the tool output being discussed), so the suite also runs without
a key — a key just makes the tool-calling path observable.

## Results

Each run writes `evals/results/<timestamp>/` — `aggregate-result.json` plus the HTML
report — and the directory is git-ignored.

## Case format

```yaml
schema_version: "1.0"
name: extract-over-search
prompt: |
  <the user prompt>
execution:
  prompt: |
    <the same user prompt — the installed CLI requires execution.prompt>
  max_turns: 6
  timeout_seconds: 120
graders:
  - type: llm
    name: short-grader-name
    criteria: >-
      What must be true of the final answer, including the failure conditions.
```

Notes:

- `schema_version` is `"1.0"`; `name` should match the case directory.
- The prompt appears twice: the top-level `prompt` and `execution.prompt`. The
  runner takes the prompt from `execution.prompt` when it runs the case; the
  top-level copy keeps the file readable and schema-compatible with the
  `prompt.md` form. Keep the two identical when editing a case.
- `max_turns` and `timeout_seconds` bound the run (they live under `execution`).
- Grader types supported by the CLI: `llm` (preferred — describe what must be
  true and what counts as a fail), `regex`, `tool_used` (`tool: <name>`),
  `tool_order` (`before` / `after` tool objects), `file_exists` and `baseline`.
- Every case here uses an LLM grader deliberately: the point is whether the model
  follows the skills' routing and reporting rules, not whether it emits an exact
  string.

## Cases

| Case | What it checks |
| --- | --- |
| `extract-over-search` | "Read this page" routes to extract, not search |
| `platform-failure-reported` | `data.success: false` inside HTTP 200 is reported as a failure |
| `timeout-no-retry` | No retry of a timed-out billed call; hand off the `request_id` and the console Logs |
| `monitor-confirm-webhook` | Monitoring asks for confirmation and a public webhook before creating a job |
| `search-dictionaries` | Search country/language come from the right dictionaries; language codes are case-sensitive |
| `quote-request-id` | Every reported result quotes the actual `request_id` |
| `template-list-get-run` | Templates go list -> get -> run; no hand-written selectors |
| `map-site-pages` | "Which pages exist on this site" routes to map |
