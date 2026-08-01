#!/usr/bin/env python3
"""game-wire-lint.py — mechanical gate for `contracts/game-wire/`.

WHY THIS EXISTS (CWC-Q4, decided at scaffolding 2026-07-27). The two existing
contract gates in this repo don't fit game-wire, for the same reason:

  • `TestOpenAPIRouteConformance` walks a live chi router — game-wire has no
    HTTP routes.
  • the frontend-tools contract test regenerates a snapshot FROM code
    (`WRITE_FRONTEND_CONTRACT=1 pytest`) — game-wire is contract-FIRST: the
    schema exists precisely because the producer and consumer don't yet.

So the gate is a schema-INTEGRITY lint over the hand-authored SoT, enforcing
the invariants doc 20 states in prose. Producer-side conformance tests are
added per language as producers appear (Rust `TurnOutcome` projection is the
first, in commit-service).

CHECKS
  json          each file parses, declares $schema + $id
  refs          every $ref resolves (internal `#/$defs/X` and cross-file
                `other.schema.json#/$defs/X`)
  bigint        CWC-A2 — no `*_id` / `turn_number` / `*_event_id` property may
                be a JSON number. 64-bit ids MUST cross the wire as strings;
                JS `number` corrupts silently past 2^53. This is the check
                that exists because the bug class is invisible in testing:
                small ids round-trip fine right up until production ids don't.
  closed        every object with `properties` sets `additionalProperties:
                false`, and every `enum` is a string enum. Open objects are how
                a field silently drifts between two languages joined only by a
                wire (the `panel_id` free-string bug, Frontend-Tool-Contract).

EXIT: 0 = clean · 1 = findings · 2 = usage/config error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_DIR = os.path.join(REPO_ROOT, "contracts", "game-wire")

# Property names that carry a 64-bit server-side integer. `*_id` is the broad
# rule; these are the ones that don't end in `_id`.
BIGINT_NAMES = {"turn_number", "channel_event_id", "from_tokens"}
BIGINT_SUFFIX = re.compile(r"_id$")
# `$ref` targets that are legitimate string carriers for an id-shaped field.
STRING_ID_REFS = ("Uint64String", "EntityId", "Uuid", "Digest")


def die(msg: str):
    print(f"game-wire-lint: error: {msg}", file=sys.stderr)
    sys.exit(2)


def walk(node, path, fn):
    """Depth-first over the schema tree, calling fn(node, path) on dicts."""
    if isinstance(node, dict):
        fn(node, path)
        for k, v in node.items():
            walk(v, f"{path}/{k}", fn)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f"{path}[{i}]", fn)


def resolve_ref(ref: str, docs: dict[str, dict], self_name: str, root: str) -> bool:
    file_part, _, frag = ref.partition("#")
    target_name = self_name if not file_part else file_part
    doc = docs.get(target_name)
    if doc is None and file_part:
        # Cross-contract reference (e.g. ../agent/decision.schema.json — the
        # Decision envelope is owned by contracts/agent and referenced here,
        # never copied). Resolve it off disk and cache it.
        candidate = os.path.normpath(os.path.join(root, file_part))
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as fh:
                    doc = json.load(fh)
                docs[target_name] = doc
            except json.JSONDecodeError:
                return False
    if doc is None:
        return False
    if not frag:
        return True
    node = doc
    for part in frag.strip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def main() -> int:
    ap = argparse.ArgumentParser(prog="game-wire-lint.py")
    ap.add_argument("--path", default=DEFAULT_DIR, help="contracts/game-wire dir")
    args = ap.parse_args()

    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        die(f"not a directory: {root}")

    files = sorted(f for f in os.listdir(root) if f.endswith(".schema.json"))
    if not files:
        die(f"no *.schema.json under {root}")

    findings: list[str] = []
    docs: dict[str, dict] = {}

    # ── json ──
    for fn in files:
        p = os.path.join(root, fn)
        try:
            with open(p, "r", encoding="utf-8") as fh:
                docs[fn] = json.load(fh)
        except json.JSONDecodeError as e:
            findings.append(f"{fn}: [json] not valid JSON: {e}")
            continue
        for required in ("$schema", "$id"):
            if required not in docs[fn]:
                findings.append(f"{fn}: [json] missing top-level `{required}`")

    # ── refs · bigint · closed ──
    # list(): resolve_ref caches cross-contract docs into `docs` as it goes.
    for fn, doc in list(docs.items()):
        def check(node, path, _fn=fn):
            if "$ref" in node and isinstance(node["$ref"], str):
                if not resolve_ref(node["$ref"], docs, _fn, root):
                    findings.append(
                        f"{_fn}: [refs] unresolvable $ref `{node['$ref']}` at {path}")

            if "enum" in node and isinstance(node["enum"], list):
                if node.get("type") not in ("string", "integer"):
                    findings.append(
                        f"{_fn}: [closed] enum without an explicit string/integer "
                        f"`type` at {path}")

            props = node.get("properties")
            if isinstance(props, dict):
                if node.get("additionalProperties") is not False:
                    findings.append(
                        f"{_fn}: [closed] object with `properties` must set "
                        f"`additionalProperties: false` at {path}")
                for name, spec in props.items():
                    if not isinstance(spec, dict):
                        continue
                    suspect = name in BIGINT_NAMES or BIGINT_SUFFIX.search(name)
                    if not suspect:
                        continue
                    ref = spec.get("$ref", "")
                    ok_ref = any(r in ref for r in STRING_ID_REFS)
                    ok_str = spec.get("type") == "string"
                    ok_obj = spec.get("type") == "object"  # from_tokens map
                    if not (ok_ref or ok_str or ok_obj):
                        findings.append(
                            f"{_fn}: [bigint] `{name}` at {path} is not a string "
                            f"(CWC-A2: 64-bit ids cross the wire as decimal "
                            f"strings — JS number corrupts past 2^53)")

        walk(doc, fn, check)

    print(f"game-wire-lint: scanned {len(docs)} schema file(s) under {root}")
    for f in findings:
        print(f)
    if findings:
        print(f"\ngame-wire-lint: FAIL — {len(findings)} finding(s)")
        return 1
    print("game-wire-lint: OK — schemas coherent "
          "(refs resolve · ids are strings · objects closed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
