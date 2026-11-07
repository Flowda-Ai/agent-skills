# `spec/` — the contract snapshot

`openapi.snapshot.json` is a copy of the OpenAPI document that the developer API
serves at <https://openapi.flowda.ai/v1/openapi.json>. The document itself is
generated from `flowda-web-openapi/internal/router/assets/developer-openapi.yaml`.

It is committed here because two scripts depend on it and neither should need the
network at review time:

- `scripts/gen_references.py` renders `skills/flowda/references/params/*.md` from it;
- `scripts/validate_skills.py` checks `scripts/tool_map.py` against it.

`SOURCE.json` records where the copy came from, when it was fetched, and its
SHA-256; every generated reference file embeds the first 16 hex characters of that
digest, so a diff of a generated file points at the document revision that caused
it.

## Refreshing

```powershell
python scripts/sync_contract.py            # fetch https://openapi.flowda.ai/v1/openapi.json
python scripts/sync_contract.py --check    # compare only; exit 1 when the live document moved
python scripts/gen_references.py           # regenerate the field tables
python scripts/validate_skills.py          # release gate
```

Do not edit either JSON file by hand. If the API changed, also check
`scripts/tool_map.py` (tool names, budgets, credit estimates) and any prose that
quotes a limit.
