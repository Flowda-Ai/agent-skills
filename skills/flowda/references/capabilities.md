# Choosing a capability, and how they chain

Five capabilities share one fetch network, one credential and one billing account.
Pick by what the user already has, not by which tool sounds closest.

| Capability | Answers | Returns | Cost | Use something else when |
| --- | --- | --- | --- | --- |
| `flowda_extract` | "What does this page say?" | The page in the formats you asked for: `markdown`, `raw_html`, `clean_html`, `links` | 1 on a cache hit, else 1 / 3 / 5 by strategy | The URL is unknown (search) or the site is a supported retailer with a template (template) |
| `flowda_search` | "What is out there about X?" | Result list: `position`, `title`, `url`, `snippet` (plus `date` for news), optionally each result's extracted content | Per returned result; 0 when nothing is returned | The user already named the URL (extract) or wants one site's URL list (map) |
| `flowda_map` | "Which pages exist on this site?" | `{url, title?, description?}` entries | By discovery volume | The user wants page content (extract) or links about a topic (search) |
| `flowda_template` | "Give me the structured fields for this Amazon/Walmart page" | Records shaped by the template's output schema; `meta.fields` describes them | Flat 5, even when the result is empty | The site is not a supported template site (extract) |
| watch tools | "Tell me when this page changes" | A job with a schedule and status; checks; diffs | About 1 credit per job call; a real check is 1 / 3 / 5 | The user wants the content once (extract) |

## What each capability actually returns

**extract** — `data.outputs` holds exactly the formats you requested. An empty string
means "produced, but nothing matched"; `null` means "requested, but could not be
produced". `data.meta.strategy_used` (`X1`/`X2`/`X3`) is what drives the price,
`data.meta.cache_hit` says whether a snapshot was reused, and
`data.meta.result.status_code` is the **target site's** status (possibly `null`) —
compare `data.meta.result.final_url` with the URL you sent to spot a redirect.

**search** — `data.outputs` is an array of results; `data.meta.count` is how many came
back. Zero results is a success (`outputs: null`, `count: 0`). With
`extract_content: true` each result also carries `extract`, and a per-result extraction
failure is reported there (`success: false` with its own `code`/`message`) without
failing the search.

**map** — `data.outputs` is an array of discovered URLs with optional `title` and
`description`; it is `null` when nothing was discovered. `data.meta.count` is the
count. It returns links, never page content.

**template** — `data.outputs` is an array of records, one record for a detail
template, `null` when there was no content. `data.meta.count` and
`data.meta.fields` (labels/descriptions keyed by field path) describe what you got. A
successful but empty result still costs 5 credits; a failed execution
(`data.success: false`) costs 0.

**watch** — a job object (`job_id`, `status`, `schedule`, `next_run_at`,
`last_error`, …), a page of checks (`diff_summary` only), or one check with its full
diff. Details and traps: [watch-lifecycle.md](watch-lifecycle.md).

## Chains that work

- **Site → content.** `flowda_map` the site with a small `limit` and
  `domain_filter: domain`, choose the few URLs the user needs, `flowda_extract` each
  one. Never extract everything a map returns: every extract is billed separately.
- **Question → sources → content.** `flowda_search` with a small `max_results`,
  then `flowda_extract` the results the user picks. When the user wants the content
  of the top results in one go, `flowda_search` with `extract_content: true` avoids a
  second round of calls, at the price of per-result extraction credits.
- **Retailer → structured data.** `flowda_templates_list` (free) → `flowda_templates_get`
  (free) for the exact input and output schema → `flowda_template`. Writing your own
  selectors is not supported; for an unsupported site use `flowda_extract`.
- **Baseline → monitor.** `flowda_watch_create` with a schedule, then — only if the
  user wants a baseline now and accepts the cost — `flowda_watch_run_check`. A first
  successful check is a baseline (`data.meta.is_baseline: true`, `changed: false`,
  `diff: null`); later changes arrive as diffs or webhook events.

## Worked examples and near-misses

1. **"What does https://example.com/pricing say?"** → `flowda_extract`. *Near miss:*
   `flowda_search` with the URL as the query — the user gave you the page, so fetch it.
2. **"Find the best espresso machine reviews."** → `flowda_search` (`max_results` is an
   upper bound, not a promise), then extract only the result the user asks about.
   *Near miss:* `flowda_map` on one blog — that enumerates URLs, it does not rank the web.
3. **"Which pages does example.com have?"** → `flowda_map`, `domain_filter: domain`,
   `limit` kept small, then summarise the URLs. *Near miss:* `flowda_extract` on the
   home page — its `links` format is the links on that page, not the site's URL set,
   and there is no crawl endpoint.
4. **"Pull the price and stock for this Amazon ASIN."** → `flowda_templates_list` →
   `flowda_templates_get` (find the identifier key, e.g. `asin`) → `flowda_template`.
   Flat 5 credits, one record. *Near miss:* `flowda_extract` on the product page: it
   returns a page representation, not the template's typed fields, and costs 1 / 3 / 5.
5. **"Get me everything on amazon.com about X."** → `flowda_templates_list` to see
   whether a search/category template covers it; if not, `flowda_search` restricted to
   that site's results, or `flowda_extract` on the specific page. Take template ids only
   from `flowda_templates_list` — an unrecognised id is rejected, with the id named in
   the error.
6. **"Tell me when this page changes."** → `flowda_watch_create`. If the user has no
   public endpoint, omit `webhook_url` and poll `flowda_watch_list_checks` instead.
   *Near miss:* calling `flowda_extract` again later — that is a one-off fetch, not a
   monitor, and it has no history or diff.
7. **"Did it change just now?"** → `flowda_watch_run_check` (a real fetch: it costs
   credits, can take up to 70s, and its result is flat). *Near miss:*
   `flowda_watch_get_check` only reads a past check; `flowda_watch_list_checks` lists
   past checks with `diff_summary` only.
8. **"What has this job seen?"** → `flowda_watch_list_checks`, then
   `flowda_watch_get_check` for the full diff of one check. A `null` diff means the
   check found no change or only established the baseline.

## Three dictionaries that are not interchangeable

- `flowda_regions` → `country` for `flowda_extract`, `flowda_map` and
  `flowda_watch_create`.
- `flowda_search_countries` → `country` for `flowda_search` (uppercase codes).
- `flowda_search_languages` → `language` for `flowda_search` (case-sensitive: pass the
  returned code back verbatim).

All three are free and need no API key, so a wrong value is caught with a free call
instead of a rejected paid one. Where a scope or key rule matters, see
[scopes.md](scopes.md); for prices and limits, [costs-and-limits.md](costs-and-limits.md).

## User says X → do Y

| User says | Do |
| --- | --- |
| "What does this page say?" (URL given) | `flowda_extract` — fetch the named URL |
| "Find recent articles about X" | `flowda_search` with `source: news` and `time_range: week`; extract only the chosen one |
| "Which pages does this site have?" | `flowda_map` with `domain_filter: domain` and a modest `limit`; summarise URLs |
| "Get the Amazon/Walmart data for this item" | `flowda_templates_list` → `flowda_templates_get` → `flowda_template` |
| "Tell me when this page changes" | `flowda_watch_create` (confirm first); webhook if they have a public endpoint, else poll `flowda_watch_list_checks` |
| "Check it right now" | `flowda_watch_run_check` (real fetch, costs credits, may take 70s) |
| "Show me what changed" | `flowda_watch_list_checks` for summaries → `flowda_watch_get_check` for the diff |
| "What can this key do?" | `flowda_account`; if a scope is missing, [scopes.md](scopes.md) |
