"""Release gate for the skill pack.

Checks, in order:

1. layout and frontmatter of every ``skills/*/SKILL.md``;
2. the canonical rules block is byte-identical in every skill;
3. every ``flowda_*`` tool name mentioned exists, and every tool is mentioned;
4. relative links resolve and capability skills stay self-contained;
5. ``skills/flowda/references/params/`` is exactly what the generator produces;
6. ``scripts/tool_map.py`` and ``spec/openapi.snapshot.json`` agree, and (when a
   ``flowda-mcp-service`` checkout is next to this repository) agree with its
   ``internal/contract/operations.go``;
7. plugin manifests and eval case files are present and well formed.

Run it before every release:

    python scripts/validate_skills.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import gen_references
import tool_map

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"

EXPECTED_SKILLS = {
    "flowda",
    "flowda-extract",
    "flowda-search",
    "flowda-map",
    "flowda-template",
    "flowda-watch",
}
# flowda is the router and carries the reference index; the capability skills stay short.
MAX_LINES = {"flowda": 220}
DEFAULT_MAX_LINES = 180
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TOOL_RE = re.compile(r"\bflowda_[a-z][a-z0-9_]*\b")
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
GRADER_TYPES = {"regex", "tool_order", "tool_used", "file_exists", "llm", "baseline"}
MAX_DESCRIPTION = 1024

errors: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("file does not start with a YAML frontmatter block")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("frontmatter is not closed with a --- line")
    raw = text[4:end].split("\n")
    body = text[end + 5 :]
    return parse_frontmatter(raw), body


def parse_frontmatter(lines: list[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if ":" not in line or line.startswith((" ", "\t")):
            raise ValueError(f"cannot parse frontmatter line: {line!r}")
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value in ("|", ">", "|-", ">-"):
            block: list[str] = []
            index += 1
            while index < len(lines) and (lines[index].startswith((" ", "\t")) or not lines[index].strip()):
                block.append(lines[index].strip())
                index += 1
            joiner = " " if value.startswith(">") else "\n"
            data[key] = joiner.join(part for part in block if part).strip()
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        data[key] = value
        index += 1
    return data


def canonical_rules() -> str:
    text = read_text(REPO / "docs" / "authoring.md")
    start_marker = "<!-- canonical-rules:start -->"
    end_marker = "<!-- canonical-rules:end -->"
    try:
        start = text.index(start_marker) + len(start_marker)
        end = text.index(end_marker)
    except ValueError as exc:  # pragma: no cover - authoring.md is part of the repo
        raise SystemExit("docs/authoring.md has no canonical-rules markers") from exc
    return text[start:end].strip("\n")


def skill_dirs() -> dict[str, Path]:
    if not SKILLS.exists():
        return {}
    return {
        path.parent.name: path
        for path in sorted(SKILLS.glob("*/SKILL.md"))
        if path.parent.parent == SKILLS
    }


def check_layout_and_frontmatter(skills: dict[str, Path]) -> dict[str, str]:
    missing = EXPECTED_SKILLS - set(skills)
    for name in sorted(missing):
        fail(f"missing skill: skills/{name}/SKILL.md")
    for name in sorted(set(skills) - EXPECTED_SKILLS):
        notes.append(f"extra skill (allowed, not required): skills/{name}")

    bodies: dict[str, str] = {}
    for name, path in skills.items():
        text = read_text(path)
        try:
            front, body = split_frontmatter(text)
        except ValueError as exc:
            fail(f"skills/{name}/SKILL.md: {exc}")
            continue
        declared = front.get("name", "")
        if declared != name:
            fail(f"skills/{name}/SKILL.md: frontmatter name {declared!r} does not match the directory")
        if not NAME_RE.match(declared or ""):
            fail(f"skills/{name}/SKILL.md: name {declared!r} is not lowercase letters/digits/hyphens")
        description = front.get("description", "")
        if not description:
            fail(f"skills/{name}/SKILL.md: missing description")
        elif len(description) > MAX_DESCRIPTION:
            fail(f"skills/{name}/SKILL.md: description is {len(description)} chars (max {MAX_DESCRIPTION})")
        elif len(description) < 40:
            fail(f"skills/{name}/SKILL.md: description is too short to trigger reliably ({len(description)} chars)")
        limit = MAX_LINES.get(name, DEFAULT_MAX_LINES)
        line_count = len(text.splitlines())
        if line_count > limit:
            fail(f"skills/{name}/SKILL.md: {line_count} lines (max {limit}); move detail into references/")
        if len(body.strip().splitlines()) < 20:
            fail(f"skills/{name}/SKILL.md: body is too short to be useful")
        for marker in ("TODO", "FIXME", "TBD", "{{"):
            if marker in body:
                fail(f"skills/{name}/SKILL.md: contains placeholder {marker!r}")
        bodies[name] = body
    return bodies


def check_canonical_block(skills: dict[str, Path], bodies: dict[str, str]) -> str:
    canonical = canonical_rules()
    for name, body in bodies.items():
        if canonical not in body:
            fail(f"skills/{name}/SKILL.md: canonical rules block is missing or edited (copy it from docs/authoring.md)")
    return canonical


def check_tool_names(bodies: dict[str, str]) -> None:
    known = tool_map.known_tools()
    mentioned: dict[str, set[str]] = {tool: set() for tool in known}
    files = list(SKILLS.rglob("*.md")) if SKILLS.exists() else []
    for path in files:
        text = read_text(path)
        for tool in TOOL_RE.findall(text):
            if tool not in known:
                fail(f"{path.relative_to(REPO)}: unknown tool name {tool!r}")
            else:
                mentioned[tool].add(str(path.relative_to(REPO)))
    for tool, where in sorted(mentioned.items()):
        if not where:
            fail(f"tool {tool} is never mentioned in skills/ (each tool needs at least one home)")


def check_links(skills: dict[str, Path]) -> None:
    for name, path in skills.items():
        skill_root = path.parent.resolve()
        for md in sorted(path.parent.rglob("*.md")):
            text = read_text(md)
            for target in LINK_RE.findall(text):
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                cleaned = target.split("#", 1)[0]
                if not cleaned:
                    continue
                resolved = (md.parent / cleaned).resolve()
                if not resolved.exists():
                    fail(f"skills/{name}/{md.relative_to(path.parent)}: broken relative link {target!r}")
                elif skill_root not in resolved.parents and resolved != skill_root:
                    fail(
                        f"skills/{name}/{md.relative_to(path.parent)}: link {target!r} escapes the skill directory, "
                        "so it breaks when the skill is installed alone"
                    )


def check_generated(params_dir: Path) -> None:
    spec, digest = gen_references.load_snapshot()
    expected = gen_references.render_all(spec, digest)
    on_disk = {path for path in params_dir.glob("*.md")} if params_dir.exists() else set()
    for path, content in expected.items():
        if not path.exists():
            fail(f"missing generated file: {path.relative_to(REPO)} (run python scripts/gen_references.py)")
        elif read_text(path) != content:
            fail(f"stale generated file: {path.relative_to(REPO)} (run python scripts/gen_references.py)")
    for path in sorted(on_disk - set(expected)):
        fail(f"unexpected file in generated directory: {path.relative_to(REPO)}")


def check_contract() -> None:
    spec, digest = gen_references.load_snapshot()
    source_path = REPO / "spec" / "SOURCE.json"
    if source_path.exists():
        source = json.loads(source_path.read_text(encoding="utf-8"))
        if source.get("sha256") != digest:
            fail("spec/SOURCE.json sha256 does not match spec/openapi.snapshot.json (rerun sync_contract.py)")
    else:
        fail("missing spec/SOURCE.json")

    operations = set(gen_references.collect_operations(spec))
    mapped = set(tool_map.TOOL_BY_OPERATION)
    for op in sorted(mapped - operations):
        fail(f"scripts/tool_map.py references operation {op!r}, which is not in the snapshot")
    for op in sorted(operations - mapped):
        fail(f"snapshot operation {op!r} has no tool entry in scripts/tool_map.py")
    if len(tool_map.OPERATION_BY_TOOL) != len(tool_map.OPERATIONS):
        fail("scripts/tool_map.py has duplicate tool names")
    if len(operations) != len(mapped):
        fail(f"operation count mismatch: spec {len(operations)}, tool map {len(mapped)}")

    go_path = REPO.parent / "flowda-mcp-service" / "internal" / "contract" / "operations.go"
    if not go_path.exists():
        notes.append("flowda-mcp-service checkout not found next to this repo; skipped the cross-repo check")
        return
    go_text = go_path.read_text(encoding="utf-8")
    for op, tool in sorted(tool_map.TOOL_BY_OPERATION.items()):
        match = re.search(rf'"{re.escape(op)}":\s*\{{([^}}]*)\}}', go_text)
        if not match:
            fail(f"operations.go has no entry for operation {op!r} (tool map claims {tool})")
            continue
        block = match.group(1)
        tool_match = re.search(r'Tool:\s*"([^"]+)"', block)
        if tool_match and tool_match.group(1) != tool:
            fail(f"tool name drift for {op}: skills repo {tool!r}, flowda-mcp-service {tool_match.group(1)!r}")
        budget_match = re.search(r"Budget:\s*(\d+)\s*\*\s*time\.Second", block)
        if budget_match and int(budget_match.group(1)) != tool_map.BUDGET_BY_OPERATION[op]:
            fail(f"budget drift for {op}: skills repo {tool_map.BUDGET_BY_OPERATION[op]}s, "
                 f"flowda-mcp-service {budget_match.group(1)}s")
        credits_match = re.search(r"Credits:\s*([\d.]+)", block)
        go_credits = float(credits_match.group(1)) if credits_match else 0.0
        if go_credits != float(tool_map.CREDITS_BY_OPERATION[op]):
            fail(f"credit estimate drift for {op}: skills repo {tool_map.CREDITS_BY_OPERATION[op]}, "
                 f"flowda-mcp-service {go_credits}")


def check_manifests() -> None:
    required = [
        REPO / ".claude-plugin" / "plugin.json",
        REPO / ".claude-plugin" / "marketplace.json",
        REPO / ".mcp.json",
        REPO / ".codex-plugin" / "plugin.json",
        REPO / "README.md",
        REPO / "docs" / "install.md",
    ]
    for path in required:
        if not path.exists():
            fail(f"missing {path.relative_to(REPO)}")
    for rel in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json", ".mcp.json", ".codex-plugin/plugin.json"):
        path = REPO / rel
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"{rel}: invalid JSON ({exc})")
            continue
        if rel.endswith("plugin.json") and rel.startswith(".claude-plugin"):
            for key in ("name", "version", "description", "author"):
                if not data.get(key):
                    fail(f"{rel}: missing required field {key!r}")
        if rel == ".mcp.json" and not (data.get("mcpServers") or {}).get("flowda"):
            fail(".mcp.json: expected mcpServers.flowda")
        if rel == ".claude-plugin/marketplace.json":
            plugins = data.get("plugins") or []
            if not any(plugin.get("name") == "flowda" for plugin in plugins):
                fail(".claude-plugin/marketplace.json: no plugin named flowda")
        if rel == ".codex-plugin/plugin.json":
            skills_path = data.get("skills")
            if not skills_path:
                fail(".codex-plugin/plugin.json: missing skills path")


def check_evals() -> None:
    evals_root = REPO / "evals"
    if not (evals_root / "README.md").exists():
        fail("missing evals/README.md")
    cases = sorted(evals_root.glob("*/case.yaml"))
    if not cases:
        fail("evals/: no case.yaml files found")
    for case in cases:
        text = read_text(case)
        for field in ("schema_version", "name", "prompt", "graders"):
            if not re.search(rf"^{field}\s*:", text, re.MULTILINE):
                fail(f"{case.relative_to(REPO)}: missing {field!r}")
        for grader_type in re.findall(r"^\s*-\s*type:\s*(\S+)\s*$", text, re.MULTILINE):
            if grader_type not in GRADER_TYPES:
                fail(f"{case.relative_to(REPO)}: unknown grader type {grader_type!r}")


def main() -> int:
    skills = skill_dirs()
    bodies = check_layout_and_frontmatter(skills)
    check_canonical_block(skills, bodies)
    check_tool_names(bodies)
    check_links(skills)
    check_generated(SKILLS / "flowda" / "references" / "params")
    check_contract()
    check_manifests()
    check_evals()

    for note in notes:
        print(f"note: {note}")
    if errors:
        print(f"\n{len(errors)} problem(s):", file=sys.stderr)
        for problem in errors:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"skills OK: {len(skills)} skills, {len(tool_map.OPERATIONS)} tools, generated references fresh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
