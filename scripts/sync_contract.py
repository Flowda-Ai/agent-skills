"""Fetch the flowda OpenAPI document and keep ``spec/openapi.snapshot.json`` fresh.

The snapshot is the single contract source for this repository: field tables are
generated from it and ``validate_skills.py`` checks the tool table against it.

Usage:
    python scripts/sync_contract.py              # fetch the live document
    python scripts/sync_contract.py --check      # fail if the live document moved
    python scripts/sync_contract.py --file PATH  # use a local document instead
    python scripts/sync_contract.py --url URL    # override the source URL

Exit codes: 0 unchanged/written, 1 differs under --check, 2 fetch/parse error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SNAPSHOT = REPO / "spec" / "openapi.snapshot.json"
SOURCE = REPO / "spec" / "SOURCE.json"
DEFAULT_URL = "https://openapi.flowda.ai/v1/openapi.json"


def load_bytes(args: argparse.Namespace) -> bytes:
    if args.file:
        return Path(args.file).read_bytes()
    request = urllib.request.Request(
        args.url,
        headers={"Accept": "application/json", "User-Agent": "flowda-agent-skills-sync"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def operations(document: dict) -> list[str]:
    found: list[str] = []
    for path, item in document.get("paths", {}).items():
        for method, operation in item.items():
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                found.append(operation.get("operationId", f"{method.upper()} {path}"))
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--file")
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    args = parser.parse_args()

    try:
        raw = load_bytes(args)
        document = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 - report, don't traceback
        print(f"error: could not load the OpenAPI document: {exc}", file=sys.stderr)
        return 2

    if not document.get("paths"):
        print("error: document has no paths", file=sys.stderr)
        return 2

    pretty = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    payload = pretty.encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()

    if args.check:
        if not SNAPSHOT.exists():
            print("error: no snapshot to compare against", file=sys.stderr)
            return 1
        current = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        if current == document:
            print(f"snapshot up to date ({len(operations(document))} operations, sha256 {digest[:16]})")
            return 0
        old = set(operations(current))
        new = set(operations(document))
        print("snapshot is stale:", file=sys.stderr)
        for op in sorted(new - old):
            print(f"  added   {op}", file=sys.stderr)
        for op in sorted(old - new):
            print(f"  removed {op}", file=sys.stderr)
        if old == new:
            print("  operation set unchanged; a field, description or example changed", file=sys.stderr)
        print("run: python scripts/sync_contract.py", file=sys.stderr)
        return 1

    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_bytes(payload)
    source = {
        "source": args.file or args.url,
        "fetched_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
        "sha256": digest,
        "openapi": document.get("openapi"),
        "api_version": (document.get("info") or {}).get("version"),
        "operations": len(operations(document)),
    }
    SOURCE.write_bytes((json.dumps(source, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"wrote {SNAPSHOT.relative_to(REPO)} ({len(operations(document))} operations, sha256 {digest[:16]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
