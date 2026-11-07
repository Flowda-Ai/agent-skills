# Credentials, scopes and 12015

## The credential forms

| How | Header | Notes |
| --- | --- | --- |
| API key | `Authorization: Bearer flw_<env>_<key_id>_<secret>` | Created in the console. The key's per-endpoint `scope` is enforced |
| API key | `X-API-Key: <key>` | Equivalent form; `Authorization` wins when both are present |
| Console session | `Authorization: Bearer <JWT>` or the console session cookie | Obtained by signing in to the console. A session **is the account owner**, so scopes are **not** enforced |

## MCP accepts API keys only

The MCP layer has exactly one credential type: an API key. Its only local check is
shape — the credential must start with `flw_` — so a console **session JWT is
rejected** instead of silently becoming the account owner, which would bypass every
scope in `/v1`. In stdio mode `FLOWDA_API_KEY` must be a `flw_…` key for the same
reason.

Practical consequences:

- Never paste a console session token into an MCP client configuration: the gateway
  rejects it, and a session must never be used as a shared MCP credential.
- If the user only has a session, tell them to create an API key in the console with
  the scopes they need, and configure that key in the MCP client.
- The MCP layer does not validate the key. It forwards it to `/v1`, which decides auth,
  scope, rate limit, quota and billing. There is no second path to the fetch platform.

## Scope → capability map

| Scope | Tools it enables |
| --- | --- |
| `extract` | `flowda_extract`, `flowda_template`, `flowda_templates_list`, `flowda_templates_get` |
| `search` | `flowda_search` |
| `map` | `flowda_map` |
| `watch` | `flowda_watch_create`, `flowda_watch_list`, `flowda_watch_get`, `flowda_watch_update`, `flowda_watch_delete`, `flowda_watch_run_check`, `flowda_watch_pause`, `flowda_watch_resume`, `flowda_watch_list_checks`, `flowda_watch_get_check` |

Three reads are free and **public** — no key at all: `flowda_regions`,
`flowda_search_countries`, `flowda_search_languages`. `flowda_account` is free (0
credits) but needs a valid API key, because it reports that key's scopes and quota.

The MCP layer also filters which tools it lists, per credential: the visible subset is
decided by the scopes returned from `GET /v1/account` (cached 300s), so a key without
`watch` does not see the watch tools, and a credential where scope enforcement is off
sees everything. A tool missing from the list is therefore a scope hint — but
`tools/call` is always forwarded, so a refused call still returns the real 403.

## 403 with code 12015 — the scope denial

A missing scope is **403, not 401**: the key is valid, the grant is not. The API puts
the missing scope in `data.required_scope` — the only failure that carries `data` —
and the MCP result surfaces it as a top-level `required_scope`:

```json
{"ok": false, "code": 12015, "message": "api key scope denied",
 "request_id": "req_6a99053110d62d17", "required_scope": "map", "hint": "…"}
```

`flowda_account` is the first call in every scope investigation, and it keeps working
during a 403 because it answers from the already-resolved credential instead of
querying the database. Read `scopes`, `scope_enforced`, `key_id` (empty for session
calls) and `daily_credit_quota` (`0` means unlimited).

Do not confuse the 4xx family around credentials:

- `12001` / `12002` — no credential sent / a session token that is invalid or
  expired. Sign in again, or configure the key.
- `12014` — the API key itself is invalid, revoked or expired: check the key in the
  console.
- `12003` — forbidden for another reason (account disabled, or a console write failed
  its origin check); it is not a scope problem and adding a scope will not help.
- `12015` — valid key, missing scope. Add the scope; do not rotate the key.

## Fixing a 12015 for the user

1. Call `flowda_account` and read `scopes`; take `required_scope` from the failed
   call's result.
2. Tell the user to open that API key in the console and add the missing scope, or to
   issue a new key that carries it. The key id is public; the secret is not — never
   print a key.
3. After the grant is added, the call can be retried: a scope refusal runs nothing, so
   no credits were spent and rule 4 does not block the retry.

Never blame the key or suggest rotating it for a 12015, and never present the scope
denial as a successful call. Quote the `request_id` so the refusal can be traced.

Human documentation: <https://docs.flowda.ai>. Costs, quota and rate limits per key:
[costs-and-limits.md](costs-and-limits.md).
