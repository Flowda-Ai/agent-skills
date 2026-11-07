# Errors: envelope codes, platform codes, and how to word a failure

Two layers can fail, and you must check both:

1. **The flowda envelope** — non-zero `code` with an HTTP status (401/402/403/404/405/
   409/429/500/502/503/504). The tool returns `ok: false` with `code`, `message`,
   `request_id`, and `details` for the codes marked below.
2. **The fetch platform** — HTTP 200, outer `code: 0`, but `data.success: false` with a
   platform `code` (`TARGET_…`, `TEMPLATE_MISMATCH`, …). This is a failure, not a
   successful fetch.

A 2xx capability response **without** `data.success` is also treated as a failure by
the MCP layer: that shape means a proxy, a misrouted base URL or a dropped body.
Only `flowda_account` and the three dictionaries legitimately omit the field.

## Envelope codes (complete)

| Code | HTTP | Meaning | What you must do | Retry? |
| --- | --- | --- | --- | --- |
| `10000` | 500 | Internal error on flowda's side | Report it with the `request_id`; contact flowda if it persists | Transient, but never blind — see the note below |
| `11000` | 400 | Invalid request (our validation) | Fix the fields named in `details`; do not repeat the call unchanged | No |
| `11004` | 404 | Not found | Check the path/id, and that a job or check belongs to this account. If **every** `/v1` route 404s, the operator has switched the developer surface off — there is nothing to retry | No |
| `11005` | 405 | Method not allowed | Use the documented method (the tools already do) | No |
| `12001` | 401 | Authentication required | No credential was sent: configure an API key in the MCP client | No |
| `12002` | 401 | Invalid or expired session token | Sign in again; for MCP use an API key instead of a session | No |
| `12003` | 403 | Forbidden | Account disabled, or a console write request failed its origin check | No |
| `12014` | 401 | API key invalid, revoked or expired | Check and rotate the key in the console | No |
| `12015` | 403 | API key lacks this endpoint's scope | Add the scope named in `data.required_scope`; the key itself is valid. See [scopes.md](scopes.md) | No — fix the grant |
| `13000` | 429 | Rate limit exceeded | Back off for the `Retry-After` time, then retry; reduce concurrency | Yes, after `Retry-After` |
| `13002` | 402 | Daily quota exhausted | Stop for the day; the quota resets at UTC midnight. `details` shows the limit | No — not until the next UTC day |
| `14000` | 500 | Storage unavailable | Report it; contact flowda if it persists | Transient, but never blind |
| `16000` | 502 | The fetch service failed | Report it with the `request_id` | Transient, but never blind |
| `16001` | 504 | The fetch service did not answer in time | Report it; the fetch may already have run and been billed | No blind retry |
| `16002` | 400 | The fetch service rejected the request | Fix what `details` names. For extract: `EXTRACTION_SELECTION_EMPTY` (`exclude_tags` removed all body text) or `EXTRACTION_OUTPUT_TOO_LARGE` (reduce `formats`). For templates: unknown `template_id`, unsupported query parameter, invalid field | No — fix the request |
| `16003` | 429 | The fetch service is rate limiting | Reduce concurrency and back off. The fetch may have been attempted, so confirm before retrying a billed call | Transient, but never blind |
| `16004` | 402 | The fetch service has no credits left | Contact flowda to top up; retrying cannot help | No |
| `16005` | 503 | The fetch service is unreachable | Report it with the `request_id` | Transient, but never blind |
| `16006` | 400 | `webhook_url` rejected | Fix the URL: it must be a public host on port 80 or 443 (production requires https); `details` explains. Or omit `webhook_url` and poll instead. See [watch-lifecycle.md](watch-lifecycle.md) | No |
| `16007` | 401 | Webhook signature invalid | Only returned on the platform callback endpoint, not by a tool call: report it to flowda | No |
| `16008` | 409 | Conflicts with the job's current state | `details` names the conflict (for example `JOB_PAUSED`, or a check already running). Resume the job or wait; repeating the same call fails again | No |
| `16009` | 500 | Configuration problem on flowda's side | Contact flowda. Retrying will not help, and it is **not** your API key | No |

`details` is present only for `11000`, `13002`, `16002`, `16004`, `16006` and
`16008`. For `12015` the missing scope arrives in `data.required_scope` instead — that
is the only failure that carries `data`.

### Retryability, precisely

The API's own advice is "retry later" for `10000`, `14000`, `16000`, `16001` and
`16005`, "reduce concurrency and retry" for `16003`, and "back off using `Retry-After`"
for `13000`. But there is no idempotency key, and a `16xxx` code comes from the fetch
service, which may already have run the fetch and billed it. So:

- **Never retry a billed call in the same turn.** Report the platform code and the
  `request_id`, and tell the user to check the console Logs.
- **Safe to repeat:** `flowda_account`, `flowda_regions`, `flowda_search_countries`,
  `flowda_search_languages`, `flowda_templates_list`, `flowda_templates_get`.
- **Safe to retry after fixing the cause:** a scope refusal (`12015`, nothing ran), a
  request the fetch service rejected (`16002`, nothing ran), and a `429` (`13000`, the
  limiter refused the request) once `Retry-After` has passed.

## Platform codes (`data.code`)

The lists below are what each endpoint can currently produce; anything else is handled
like `UNKNOWN_ERROR`. Treat them all as failures and never present one as a fetch.

**extract**: `TARGET_TIMEOUT`, `TARGET_DNS_ERROR` (the host, or a redirect target,
could not be resolved), `TARGET_SSL_ERROR`, `TARGET_SITE_ERROR` (unreachable, redirect
loop, invalid redirect, non-routable address), `TARGET_ALL_ENGINES_FAILED` (every
retrieval engine failed, or the page has no readable content — a JavaScript-only page
also lands here: the documented remedy is to retry with `advanced_mode`),
`TARGET_UNSUPPORTED_FILE_TYPE` (a file type flowda does not deliver), `UNKNOWN_ERROR`.

**template**: `TARGET_SITE_ERROR`, `TARGET_DNS_ERROR`, `TARGET_TIMEOUT`,
`TARGET_SSL_ERROR`, `TARGET_ALL_ENGINES_FAILED`, `TEMPLATE_MISMATCH` (the page no
longer matches the template contract — re-read `flowda_templates_get` and check the
identifier), `UNKNOWN_ERROR`. A missing product or an empty listing is **not** one of
these: it is a success with `outputs: null`, and it is billed.

**map**: `INVALID_REQUEST`, `INVALID_API_KEY`, `INSUFFICIENT_CREDITS`,
`RATE_LIMITED`, `INTERNAL_ERROR`, `TARGET_ALL_ENGINES_FAILED`, `TARGET_TIMEOUT`,
`UNKNOWN_ERROR`. `INSUFFICIENT_CREDITS` and `RATE_LIMITED` here are billing and rate
conditions, not a bad URL.

**search**: no per-call platform-code list is documented. A per-result extraction
failure is reported inside `data.outputs[].extract` (`success: false` with its own
`code`/`message`) and does not fail the call; a platform-level failure uses the same
`data` shape as every other capability.

**watch**: a past check carries its own failure code in `data.data.check.code` (for
example `TARGET_SITE_ERROR`, `INTERNAL_ERROR`) and its `message`; `flowda_watch_run_check`
reports a platform failure in the usual `data` shape. A non-empty check `error` field
means no baseline or diff was produced for that run — it does not by itself mean the
call failed.

## Two request identifiers

- The envelope `request_id` (`req_…`) is flowda's. Every result quotes it.
- `data.request_id` is the fetch platform's and matches the `X-Upstream-Request-Id`
  response header. The MCP result exposes it as `upstream_request_id`.
- For `flowda_map` the value inside `data` may be the fetch network's own identifier;
  `upstream_request_id` is the one to quote when tracing a single call.

Quote both in a support request; never invent one, and never rewrite one.

## How to word a failure to the user

- Name the **platform code** when the fetch service produced it, and the envelope code
  when flowda rejected the call. Do not translate either into a guess.
- Always include the `request_id` (and the `upstream_request_id` when present).
- Never claim success, never say the page was fetched, and never fill the gap with
  content you assume is on the page.
- Say what is safe next: check the console Logs, fix the scope/key, fix the request, or
  wait for the next UTC day.

Examples:

> Could not retrieve `https://example.com/pricing`: the fetch service reported
> `TARGET_DNS_ERROR` ("The target host could not be resolved."). This is a failure on
> the target side, not your key. `request_id` `req_a1b2…`. Retrying would be a new
> billed call, so check the console Logs first.

> Your API key is valid but does not carry the `map` scope (`12015`,
> `request_id` `req_…`). Add the `map` scope in the console and the call can be
> retried — the refused call did not run.

> The request was rejected before fetching (`16002`): "Unknown template_id
> \"walmart_productt\"". Fix the template id — `flowda_templates_list` has the current
> ids — and call again.
