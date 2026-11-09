"""Generate the field references under ``skills/flowda/references/params/``.

Everything mechanical comes from the contract snapshot; nothing here is typed by
hand. Run it after ``sync_contract.py`` and commit the result:

    python scripts/gen_references.py
    python scripts/gen_references.py --check   # fail if the files are stale

``validate_skills.py`` calls the same renderer, so a stale generated file is a
release-gate failure rather than a review comment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import tool_map

REPO = Path(__file__).resolve().parent.parent
SNAPSHOT = REPO / "spec" / "openapi.snapshot.json"
OUT_DIR = REPO / "skills" / "flowda" / "references" / "params"

METHODS = {"get", "post", "put", "patch", "delete"}


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def load_snapshot(path: Path = SNAPSHOT) -> tuple[dict, str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def deref(spec: dict, node) -> dict:
    """Follow ``$ref`` chains (the document only uses local references)."""
    seen = 0
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/"):
            raise ValueError(f"unsupported $ref {ref!r}")
        target = spec
        for part in ref[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        node = target
        seen += 1
        if seen > 16:
            raise ValueError(f"$ref chain too deep at {ref!r}")
    return node if isinstance(node, dict) else {}


def collect_operations(spec: dict) -> dict[str, dict]:
    """Return operationId -> {method, path, operation, shared_parameters}."""
    found: dict[str, dict] = {}
    for path, item in spec.get("paths", {}).items():
        shared = [deref(spec, parameter) for parameter in (item.get("parameters") or [])]
        for method, operation in item.items():
            if method.lower() not in METHODS:
                continue
            op_id = operation.get("operationId")
            if not op_id:
                raise ValueError(f"{method.upper()} {path} has no operationId")
            found[op_id] = {
                "method": method.upper(),
                "path": path,
                "operation": operation,
                "shared_parameters": shared,
            }
    return found


# --------------------------------------------------------------------------- #
# field extraction
# --------------------------------------------------------------------------- #
def scope_of(op: dict) -> str:
    if op["operation"].get("security") == []:
        return "public (no API key)"
    tags = op["operation"].get("tags") or []
    tag = tags[0] if tags else ""
    if tag == "account":
        return "any valid API key"
    # The template endpoints need the same scope as POST /v1/template.
    return {"extract": "extract", "template": "extract", "search": "search", "map": "map", "watch": "watch"}.get(
        tag, tag or "unknown"
    )


def type_of(spec: dict, schema: dict) -> str:
    schema = deref(spec, schema)
    kind = schema.get("type")
    if isinstance(kind, list):
        return " | ".join(str(k) for k in kind)
    if kind == "array":
        return f"array<{type_of(spec, schema.get('items') or {})}>"
    if kind == "object" or "properties" in schema:
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return f"object<string, {type_of(spec, additional)}>"
        return "object"
    return str(kind or "any")


def notes_of(schema: dict) -> str:
    parts: list[str] = []
    description = (schema.get("description") or "").strip()
    if description:
        parts.append(description)
    enum = schema.get("enum")
    if enum:
        parts.append("one of " + ", ".join(f"`{value}`" for value in enum))
    default = schema.get("default")
    if default is not None and default != "" and not isinstance(default, (dict, list)):
        shown = default if isinstance(default, str) else json.dumps(default)
        parts.append(f"default `{shown}`")
    low, high = schema.get("minimum"), schema.get("maximum")
    if low is not None and high is not None:
        parts.append(f"range {low}–{high}")
    elif low is not None:
        parts.append(f"min {low}")
    elif high is not None:
        parts.append(f"max {high}")
    if schema.get("nullable"):
        parts.append("nullable")
    pattern = schema.get("pattern")
    if pattern and len(pattern) <= 64:
        parts.append(f"matches `{pattern}`")
    return " · ".join(parts)


def flatten_fields(spec: dict, schema: dict, prefix: str = "", depth: int = 0) -> list[dict]:
    """Flatten an object schema into table rows, recursing two levels down."""
    schema = deref(spec, schema)
    required = set(schema.get("required") or [])
    rows: list[dict] = []
    for name, raw in (schema.get("properties") or {}).items():
        sub = deref(spec, raw)
        field = f"{prefix}{name}"
        rows.append(
            {
                "field": field,
                "type": type_of(spec, sub),
                "required": "yes" if name in required else "no",
                "notes": notes_of(sub) or "—",
            }
        )
        nested = sub
        child_prefix = f"{field}."
        if sub.get("type") == "array" and isinstance(sub.get("items"), dict):
            nested = deref(spec, sub["items"])
            child_prefix = f"{field}[]."
        if depth < 2 and nested.get("type") == "object" and nested.get("properties"):
            rows.extend(flatten_fields(spec, nested, child_prefix, depth + 1))
    return rows


def cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def table(rows: list[dict], header: list[str]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(cell(row[key]) for key in header) + " |")
    return lines


def operation_block(spec: dict, op_id: str, op: dict) -> list[str]:
    tool = tool_map.TOOL_BY_OPERATION[op_id]
    budget = tool_map.BUDGET_BY_OPERATION[op_id]
    credits = tool_map.CREDITS_BY_OPERATION[op_id]
    credits_text = f"{credits:g} credit" if credits else "0 credits"
    lines = [
        f"### `{tool}` · `{op['method']} {op['path']}`",
        "",
        f"Scope `{scope_of(op)}` · `/v1` budget {budget}s · gateway pre-charge {credits_text}.",
        "",
    ]

    parameters = op["shared_parameters"] + [deref(spec, p) for p in (op["operation"].get("parameters") or [])]
    if parameters:
        rows = []
        for parameter in parameters:
            schema = deref(spec, parameter.get("schema") or {})
            rows.append(
                {
                    "field": parameter.get("name", ""),
                    "in": parameter.get("in", ""),
                    "type": type_of(spec, schema),
                    "required": "yes" if parameter.get("required") else "no",
                    "notes": notes_of(schema) or parameter.get("description", "") or "—",
                }
            )
        lines += table(rows, ["field", "in", "type", "required", "notes"]) + [""]

    body = op["operation"].get("requestBody")
    if body:
        body_resolved = deref(spec, body)
        content = body_resolved.get("content") or {}
        media = content.get("application/json") or next(iter(content.values()), None)
        schema = media.get("schema") if media else None
        rows = flatten_fields(spec, schema) if schema else []
        if rows:
            lines += table(rows, ["field", "type", "required", "notes"]) + [""]
            lines += [
                "Body field names are identical for `application/json` and "
                "`application/x-www-form-urlencoded`.",
                "",
            ]
        elif not parameters:
            lines += ["This tool takes no arguments.", ""]

        # The document's own request example is the only example we can emit
        # without inventing data. It is the same object an MCP client passes as
        # the tool's `arguments`.
        example = body_resolved.get("example")
        if isinstance(example, dict) and example:
            lines += [
                "**Example arguments** (what a client passes as the tool's `arguments`):",
                "",
                "```json",
                json.dumps(example, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
    elif not parameters:
        lines += ["This tool takes no arguments.", ""]
    else:
        lines += ["No request body; send the path/query parameters above.", ""]
    return lines


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def render_all(spec: dict, digest: str) -> dict[Path, str]:
    operations = collect_operations(spec)
    described = {tool_map.TOOL_BY_OPERATION[op] for op in operations if op in tool_map.TOOL_BY_OPERATION}
    missing = tool_map.known_tools() - described
    if missing:
        raise ValueError(f"spec snapshot is missing operations for tools: {sorted(missing)}")

    outputs: dict[Path, str] = {}
    for group in tool_map.GROUPS:
        pairs = tool_map.tools_in_group(group)
        if not pairs:
            continue
        lines = [
            "<!-- Generated by scripts/gen_references.py from spec/openapi.snapshot.json "
            f"(sha256 {digest[:16]}). DO NOT EDIT. -->",
            f"# {tool_map.GROUP_TITLES[group]}",
            "",
            "Field names are the JSON body names; MCP clients see the same names in the",
            "tool's `inputSchema`, so this file is a fallback for raw-HTTP calls and for",
            "reading a `16002` message that names a field.",
            "",
        ]
        for op_id, _tool in pairs:
            op = operations.get(op_id)
            if op is None:
                raise ValueError(f"spec snapshot has no operation {op_id!r}")
            lines += operation_block(spec, op_id, op)
        outputs[OUT_DIR / f"{group}.md"] = "\n".join(lines).rstrip() + "\n"
    return outputs


def check() -> int:
    spec, digest = load_snapshot()
    expected = render_all(spec, digest)
    problems = 0
    on_disk = {path for path in OUT_DIR.glob("*.md")} if OUT_DIR.exists() else set()
    for path, content in expected.items():
        if not path.exists():
            print(f"missing generated file: {path}", file=sys.stderr)
            problems += 1
        elif path.read_text(encoding="utf-8") != content:
            print(f"stale generated file: {path}", file=sys.stderr)
            problems += 1
    for path in sorted(on_disk - set(expected)):
        print(f"unexpected generated file: {path}", file=sys.stderr)
        problems += 1
    if problems:
        print("run: python scripts/gen_references.py", file=sys.stderr)
        return 1
    print(f"generated references up to date ({len(expected)} files)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        return check()

    spec, digest = load_snapshot()
    expected = render_all(spec, digest)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in expected.items():
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)} ({len(content.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
