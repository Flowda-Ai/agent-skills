# Watch jobs: lifecycle, schedules, webhooks, checks

A watch job registers one page with a schedule. Checks fetch the page, compare it with
the previous check and record a diff; when something changed the job can call one
webhook. The job is created on the fetch platform under flowda's credential, but
ownership stays with the account here — only this account's jobs are visible, and
another account's job is reported as 404, not 403.

## Job states

| Status | Meaning |
| --- | --- |
| `active` | Scheduled; checks run |
| `paused` | Schedule stopped by `flowda_watch_pause`; history is kept |
| `errored` | 5 consecutive failures; a later success returns the job to `active` |

A job carries `consecutive_failures`, `last_check_at`, `last_content_hash`,
`last_error` (`at`, `message` — the same text as the originating check's `error`) and
`next_run_at`, which is jittered by up to 10% of the interval and is `null` while the
job is paused or errored. `job_id` is `job_` followed by 22 base62 characters; a check
id is `chk_` followed by 22 base62 characters. Use the ids the tools return; never
paraphrase them.

## Schedule

`schedule` is a **nested object** and must contain **exactly one** of:

- `interval_seconds` — 60 to 2592000, runs on the UTC timeline (the timezone does not
  shift it);
- `cron` — a standard five-field expression, interpreted in `timezone`, weekends
  included.

`timezone` is an IANA timezone name and defaults to `UTC`; it affects `cron` schedules
only. The old top-level `schedule_interval` / `schedule_cron` fields are rejected. A
job's `url` is immutable: to change the target, create a new job.

## Creating a job

`flowda_watch_create` needs `url` and `schedule`. Useful options: `country` (from
`flowda_regions`), `selector` with `selector_type` (`css`, the default, or `xpath`) to
monitor part of the page, `diff_modes`, `retention_days`, `webhook_url`, extra
`headers` for the checks, and `mask` (noise reduction before diffing; excludes such as
`iso_timestamp`, `unix_timestamp`, `relative_time`, `counter`, `uuid`,
`session_token`, `tracking_param`, `cache_buster`, `resource_hash`, `iframe_marker`).

- `diff_modes`: `auto` (the default), `text`, `json`; no duplicates, and `auto` cannot
  be combined with the other two. With both modes requested the result also carries
  `views.text` / `views.json`.
- `retention_days`: 0 to 365, default 30; `0` keeps check history indefinitely.
- The job comes back nested as `data.data.job`, plus a one-time `webhook_secret` when
  the `webhook_url` registered an address this account had not used before.

**Confirm before creating**: a schedule is a recurring charge. State the interval and
the expected number of checks per day (an hourly interval is about 24 checks a day,
each around 1 credit) before you call the tool.

## Reading and changing jobs

- `flowda_watch_list` — this account's jobs, filterable by `status` (`active`,
  `paused`, `errored`; lowercase), exact `url`, with `limit` 1–200 (default 50) and
  `cursor` pagination. The page is nested as `data.data.jobs` (`null` when there are no
  jobs) plus `data.data.next_cursor` (`null` on the last page).
- `flowda_watch_get` — one job by id; use it to inspect status, schedule,
  `consecutive_failures` and `last_error` after a failed check.
- `flowda_watch_update` — partial update with the same fields as creation **except
  `url`**. An omitted field is unchanged; `webhook_url: null` (or `""`) removes the
  callback; `schedule: null` is rejected — send a new schedule object instead; changing
  `selector_type` without `selector` re-validates the existing selector; re-sending the
  same values succeeds idempotently. A new callback address returns a one-time
  `webhook_secret` again.
- `flowda_watch_pause` — stops the schedule, keeps history; pausing a paused job
  succeeds.
- `flowda_watch_resume` — re-enables a paused **or errored** job and resets the
  consecutive-failure counter.
- `flowda_watch_delete` — deletes the job together with its check history and pending
  deliveries; deleting an already-deleted job still succeeds, and `data.data` is then
  `null`. Destructive: only on an explicit request.

Confirm before every state change (update, pause, resume, delete). Resuming an errored
job restarts its schedule, which means recurring cost again.

## Webhooks

`webhook_url` is where change events are delivered. Requirements:

- an absolute URL on a **public host**, port **80 or 443**; production requires
  **https**, and loopback / private / link-local addresses are rejected — a rejected
  URL comes back as `16006` with `details`;
- flowda rewrites the address to its own relay before handing the job to the platform,
  and swaps the user's address back in every response, so the address the user
  configured is what they see.

If the account has never used that callback address, the response (on create or
update) carries `data.data.webhook_secret` **exactly once**. Tell the user to store it
now: it is the HMAC key the callbacks are signed with, and it is never returned again —
not by `flowda_watch_get`, not in the list.

### The callback contract

flowda `POST`s to the configured address with `Content-Type: application/json`, a JSON
body holding the change event, and these headers:

| Header | Meaning |
| --- | --- |
| `X-Watch-Signature` | `t=` unix seconds, then `,v1=` a lowercase hex digest: HMAC-SHA256 over the string `<unix seconds>.<raw request body bytes>` |
| `X-Flowda-Event` | Event name; currently `watch.change_detected` |
| `X-Flowda-Event-Id` | Stable idempotency key for job, check and event — deduplicate with it |
| `X-Flowda-Delivery-Id` | Identifier of this delivery |
| `X-Flowda-Attempt` | Attempt number, starting at 1 |

Verify over the **raw body bytes received** — parsing the JSON and re-serialising it
changes the bytes and breaks the signature. Reject anything whose timestamp is more
than 5 minutes away from now, and compare digests in constant time. Answer 2xx
quickly: a non-2xx answer is retried up to **6 delivery attempts in total**, with
delays of 10s, 1m, 5m, 30m and 2h between them; 4xx answers other than 408, 425 and 429
stop immediately, and `Retry-After` is honoured up to 10 minutes.

The event body carries the job and check identifiers, a one-line
`data.check.diff_summary`, and the change under `data.diff`; `data.delivered_at` is
when the platform created the event, which is not the timestamp in the signature
header.

Each check records its delivery state in `webhook_delivery` when a callback is
configured: `status` (`pending`, `delivered`, `failed`, `retrying`), `attempt_count`,
`last_error`, `next_retry_at`.

### No public endpoint: poll instead

If the user has no public endpoint on port 80/443, omit `webhook_url` entirely and
poll `flowda_watch_list_checks` on whatever cadence the user wants. The job still runs
on its schedule and records checks; nothing is delivered. Say plainly that polling is
a manual loop, not a notification — flowda has no email or SMS delivery documented.

## Checks

A check is one fetch plus a comparison with the previous check.

- `flowda_watch_run_check` — runs a check **now**. This is a real fetch, not a query:
  it costs 1 / 3 / 5 credits by strategy (0 when the fetch failed), is synchronous
  (the platform allows about 60 seconds; the gateway budget is 70s), and has no
  idempotency key — never retry it. Its result is **flat** (`data` is
  `success`/`request_id`/`credits_used`/`meta`/`diff`), unlike every other watch
  endpoint, which nests the body one level deeper as `data.data.{job|jobs|checks|check}`.
  `meta.is_baseline: true` means this was the first successful fetch: it only
  establishes the baseline, so `changed` is `false` and `diff` is `null`. A paused job
  answers 409 `16008` (`details: ["The job is paused."]`), and so does a check that is
  already running.
- `flowda_watch_list_checks` — past checks, newest first, with `diff_summary` only (no
  diff body); `data.data.checks` is `null` when there is no history. `limit` 1–200,
  default 50, plus `cursor`.
- `flowda_watch_get_check` — one past check with its full diff. `diff` is `null` when
  nothing changed or when that check only established the baseline. This is the only
  way to read a past diff body.

`meta.error` (and the check's `error`) reports a monitoring problem (fetch, selector,
diff). A non-empty value does not mean the call failed; it means no baseline or diff
was produced for that run. `meta.selector_matched` says whether the selector matched.

A diff carries `changed`, `mode` (`text` / `json`), `summary` (`added_lines`,
`removed_lines`, `modified_lines`, `change_ratio`), `hunks` (`before`, `after`,
`change_type`, `path`), `unified_diff` for the text view, and `truncated`.

## Watch-specific failures

- `16006` (400) — `webhook_url` rejected: not a public host, or not on port 80/443, or
  not https in production. Fix the URL, or omit it and poll.
- `16008` (409) — the request conflicts with the job's current state; `details` names
  the conflict (`JOB_PAUSED`, a check already running, …). Resume the job or wait; the
  same call will fail again otherwise.
- `11004` (404) — the job or check does not exist on this account, or the developer
  surface is switched off.
- `12015` (403) — the key lacks the `watch` scope; the job tools are hidden from
  `tools/list` for such a key, but a forwarded call still returns the real 403.

The full code table, retryability and wording: [errors.md](errors.md). Credits, quota
and budgets: [costs-and-limits.md](costs-and-limits.md).
