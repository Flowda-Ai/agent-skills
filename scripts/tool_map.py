"""The only hand-maintained contract table in this repository.

Everything else about a tool — route, method, scope, field names, limits — is
derived from ``spec/openapi.snapshot.json``. This table mirrors what the OpenAPI
document cannot express, exactly like ``operations.go`` in ``flowda-mcp-service``:

* ``tool``     the MCP tool name (the mapping is deliberate: ``checkWatchJob`` is
               "run one check now", not "list checks");
* ``budget_s`` the ``/v1`` request budget from ``configs/config.yaml``;
* ``credits``  the gateway's pre-charge estimate (0 for the free read endpoints);
* ``group``    which generated field-reference file the operation belongs to.

``scripts/validate_skills.py`` fails when this table and the snapshot disagree,
and — when a ``flowda-mcp-service`` checkout sits next to this repository —
when the tool names, budgets or credit estimates drift from its
``internal/contract/operations.go``.
"""

from __future__ import annotations

# (operation_id, tool_name, budget_seconds, gateway_credits, group)
OPERATIONS: list[tuple[str, str, int, float, str]] = [
    ("account", "flowda_account", 10, 0, "meta"),
    ("listRegions", "flowda_regions", 10, 0, "meta"),
    ("listSearchCountries", "flowda_search_countries", 10, 0, "meta"),
    ("listSearchLanguages", "flowda_search_languages", 10, 0, "meta"),
    ("extract", "flowda_extract", 130, 1, "extract"),
    ("template", "flowda_template", 130, 5, "template"),
    ("listTemplates", "flowda_templates_list", 30, 1, "template"),
    ("getTemplate", "flowda_templates_get", 30, 1, "template"),
    ("search", "flowda_search", 60, 1, "search"),
    ("map", "flowda_map", 130, 1, "map"),
    ("createWatchJob", "flowda_watch_create", 30, 1, "watch"),
    ("listWatchJobs", "flowda_watch_list", 30, 1, "watch"),
    ("getWatchJob", "flowda_watch_get", 30, 1, "watch"),
    ("updateWatchJob", "flowda_watch_update", 30, 1, "watch"),
    ("deleteWatchJob", "flowda_watch_delete", 30, 1, "watch"),
    ("checkWatchJob", "flowda_watch_run_check", 70, 1, "watch"),
    ("pauseWatchJob", "flowda_watch_pause", 30, 1, "watch"),
    ("resumeWatchJob", "flowda_watch_resume", 30, 1, "watch"),
    ("listWatchChecks", "flowda_watch_list_checks", 30, 1, "watch"),
    ("getWatchCheck", "flowda_watch_get_check", 30, 1, "watch"),
]

TOOL_BY_OPERATION = {op: tool for op, tool, _, _, _ in OPERATIONS}
OPERATION_BY_TOOL = {tool: op for op, tool, _, _, _ in OPERATIONS}
BUDGET_BY_OPERATION = {op: budget for op, _, budget, _, _ in OPERATIONS}
CREDITS_BY_OPERATION = {op: credits for op, _, _, credits, _ in OPERATIONS}
GROUP_BY_OPERATION = {op: group for op, _, _, _, group in OPERATIONS}

# Group order for the generated reference files.
GROUPS = ["extract", "search", "map", "template", "watch"]

# Human-readable one-liners used by the generator's file header.
GROUP_TITLES = {
    "extract": "extract — fetch one page",
    "search": "search — web, news, shopping and scholar indexes",
    "map": "map — enumerate a site's URLs",
    "template": "template — run a maintained site template",
    "watch": "watch — recurring monitor jobs",
}


def known_tools() -> set[str]:
    return set(OPERATION_BY_TOOL)


def tools_in_group(group: str) -> list[tuple[str, str]]:
    """Return ``(operation_id, tool_name)`` pairs for a generated group."""
    return [(op, tool) for op, tool, _, _, g in OPERATIONS if g == group]
