# Cost, cache, rate limits and budgets

## Credits per call

| Call | Credits |
| --- | --- |
| `flowda_account`, `flowda_regions`, `flowda_search_countries`, `flowda_search_languages` | 0 |
| `flowda_templates_list`, `flowda_templates_get` | 0 (metadata; still written to the call log) |
| `flowda_extract` | 1 on a cache hit; 1 / 3 / 5 on a miss, by the strategy used (`data.meta.strategy_used`: `X1` / `X2` / `X3`) |
| `flowda_template` | flat 5 per execution, including a successful but empty result; 0 when the execution failed |
| `flowda_search` | per returned result; 0 when nothing is returned. Inline extraction (`extract_content: true`) is billed as well; `data.credits_used` is the total |
| `flowda_map` | by discovery volume; `data.credits_used` reports the charge and is absent when nothing was billed |
| watch tools | about 1 credit per call; `flowda_watch_run_check` is a real fetch at 1 / 3 / 5, and 0 when the fetch failed |

`data.credits_used` in the result is the truth for what this call cost — read it back to
the user instead of quoting an estimate. The gateway pre-charges an estimate (1 credit
for most calls, 5 for `flowda_template`; the zero-cost catalogue reads are pre-charged
1 for quota accounting only) to reserve quota; the estimate is not the charge.

## Free calls

Six calls cost 0 credits: the four read-only tools (`flowda_account`,
`flowda_regions`, `flowda_search_countries`, `flowda_search_languages`) and the two
template-catalogue reads (`flowda_templates_list`, `flowda_templates_get`). The three
dictionaries need no API key at all. These are the only calls that are always safe to
repeat (see [errors.md](errors.md)); they are still recorded in the account's call log.

## Cache behaviour (extract)

- `max_age_ms` defaults to `172800000` (48 hours): a platform snapshot younger than that
  is reused and costs 1 credit (`data.meta.cache_hit: true`).
- `max_age_ms: 0` forces a fresh fetch, so it costs the miss price.
- Sending your own `headers` **never** reads the snapshot cache and leaves the target
  URL marked for 48 hours. Do not send `headers` for private pages the user does not
  want re-fetched, and do not send them just to tweak a request.
- The inline extraction in `flowda_search` follows the same `max_age_ms` rule.

## Rate limits

| Bucket | Limit |
| --- | --- |
| One API key | 5 requests/s, burst 10 |
| One user (shared across that user's keys and IPs) | 20 requests/s, burst 40 |

Over the limit is HTTP 429, code `13000`, with `Retry-After`; the tool result carries
`retry_after`. Back off for that time and reduce concurrency. A fetch-service limit
arrives as 429 code `16003` instead — reduce concurrency, and remember the fetch may
have been attempted, so do not retry a billed call blindly.

MCP adds no rate limiting of its own: rps, quota and concurrency policy are decided by
`/v1`, and a 429 is passed through unchanged.

## Daily quota

- Code `13002` (HTTP 402) means the key's daily credit quota is exhausted; it resets at
  UTC midnight. `details` shows the limit.
- `flowda_account` reports `daily_credit_quota`; `0` means unlimited.
- Code `16004` (402) is different: the *fetch service* has no credits left. Topping up
  is a flowda-side action — retrying cannot help.

## Request budgets per route

The gateway allows each route a fixed budget, below. A call that exceeds its budget
surfaces as a timeout; the fetch may already have run, so treat the outcome as unknown
and do not retry. The platform's own `timeout_ms` can be lower than the route budget.

| Budget | Tools |
| --- | --- |
| 10s | `flowda_account`, `flowda_regions`, `flowda_search_countries`, `flowda_search_languages` |
| 30s | `flowda_templates_list`, `flowda_templates_get`, and every watch tool except `flowda_watch_run_check` |
| 60s | `flowda_search` |
| 70s | `flowda_watch_run_check` |
| 130s | `flowda_extract`, `flowda_template`, `flowda_map` |

A failed `flowda_template` execution and a failed `flowda_watch_run_check` fetch cost 0
credits; do not assume the same for a failed `flowda_extract`, `flowda_search` or
`flowda_map` — read `credits_used`. A timeout is not a guarantee that nothing ran:
there is no idempotency key.

## MCP-side limits

- **Request size** 256 KB; a larger body is rejected by the transport.
- **Result size** 200 KB. Beyond it the tool truncates the largest string field at a
  UTF-8 boundary and adds an explicit `truncated` marker (`field`, `original_bytes`,
  `limit_bytes`, `note`); if the payload is still too large, `data` is dropped and the
  marker explains why. Never treat a truncated result as the whole content — narrow the
  request.
- **In-flight memory guard**: when the configured in-flight cap is reached, the
  gateway answers 503 with `Retry-After: 1`. That is a local memory guard, **not** a
  quota, and it is not logged by `/v1`; do not report it as a billing limit.
- **No result cache**: a cached result would hide whether the call was billed.
- **No automatic retries on billed operations.** The six zero-cost GETs retry once
  after a transport error — never after a timeout and never after an HTTP response.
  Redirects are not followed (a 3xx is reported as an upstream failure).
- **Long calls**: `flowda_extract`'s `timeout_ms` defaults to 30000 here (platform
  default 60000, maximum 120000) because most clients abort at 60s; raise it
  deliberately for slow sites. When the client sends a progress token, the gateway
  emits progress notifications every 10s.

## Cost discipline for an agent

1. **List before you run.** `flowda_templates_list` and `flowda_templates_get` are
   free; `flowda_template` is 5 credits. Read the schema first.
2. **Don't loop over the same URL.** Every extract is billed, even a repeat that hits
   the cache (1 credit). One call, then work with the result.
3. **Prefer the cache.** Leave `max_age_ms` at its default unless the user needs
   freshness, and do not send `headers` unless the target truly needs them.
4. **Don't fan out.** `flowda_map` can return thousands of URLs and each extract costs
   1–5 credits; map, then extract only the URLs the user asked about, and tell them the
   size of the list before fetching many pages.
5. **Budget a search.** `max_results` is an upper bound — keep it small, and add
   `extract_content: true` only when the content of the results is what the user wants.
6. **Check free dictionaries, not the paid endpoint.** A wrong `country`/`language`
   value is caught by a free lookup, not by a rejected paid call.
7. **State the cost before an expensive call**, and state the recurring nature of a
   schedule before creating a watch job (an hourly interval means roughly 24 checks a
   day, each around 1 credit). See [watch-lifecycle.md](watch-lifecycle.md).
8. **Never retry a billed call.** A retry is a second charge; report the `request_id`
   and send the user to the console Logs.
