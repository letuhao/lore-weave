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


def check(path: str = DEFAULT_DIR, string_id_refs=STRING_ID_REFS) -> int:
    """The REAL checker, returning a code so `--self-test` can drive it over a
    synthetic schema directory. It used to `die()` (sys.exit) from inside the
    walk, which a case cannot catch without swallowing the whole process."""
    root = os.path.abspath(path)
    if not os.path.isdir(root):
        print(f"game-wire-lint: error: not a directory: {root}", file=sys.stderr)
        return 2

    files = sorted(f for f in os.listdir(root) if f.endswith(".schema.json"))
    # Message refinement, not detection: no files means no subjects, so the
    # subject floors below red anyway. Kept because "there are no schemas"
    # and "the schemas contain no $ref" are different problems.
    if not files:
        print(f"game-wire-lint: error: no *.schema.json under {root}", file=sys.stderr)
        return 2

    findings: list[str] = []
    docs: dict[str, dict] = {}
    subjects = {"refs": 0, "enums": 0, "objects": 0, "bigints": 0}
    id_refs_used: set[str] = set()

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
                subjects["refs"] += 1
                for r in STRING_ID_REFS:
                    if r in node["$ref"]:
                        id_refs_used.add(r)
                if not resolve_ref(node["$ref"], docs, _fn, root):
                    findings.append(
                        f"{_fn}: [refs] unresolvable $ref `{node['$ref']}` at {path}")

            if "enum" in node and isinstance(node["enum"], list):
                subjects["enums"] += 1
                if node.get("type") not in ("string", "integer"):
                    findings.append(
                        f"{_fn}: [closed] enum without an explicit string/integer "
                        f"`type` at {path}")

            props = node.get("properties")
            if isinstance(props, dict):
                subjects["objects"] += 1
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
                    subjects["bigints"] += 1
                    ref = spec.get("$ref", "")
                    ok_ref = any(r in ref for r in STRING_ID_REFS)
                    ok_str = spec.get("type") == "string"
                    # NARROWED. This was `spec.get("type") == "object"` for ANY
                    # suspect name, under a comment naming ONE of them — so
                    # `player_id: {type: object}` satisfied CWC-A2 by being the
                    # wrong shape entirely. The exemption and its stated reason
                    # were different sizes (`GTD-18`).
                    ok_obj = name == "from_tokens" and spec.get("type") == "object"
                    if not (ok_ref or ok_str or ok_obj):
                        findings.append(
                            f"{_fn}: [bigint] `{name}` at {path} is not a string "
                            f"(CWC-A2: 64-bit ids cross the wire as decimal "
                            f"strings — JS number corrupts past 2^53)")

        walk(doc, fn, check)

    # ── SUBJECT FLOORS (GT-F3). Each rule's subject can vanish on its own: a
    # schema restructure that inlines every `$ref`, drops every closed object, or
    # renames every id property leaves the corresponding rule checking nothing
    # while the gate still says "schemas coherent". Measured 2026-08-12 across 4
    # files: 33 refs, 13 enums, 22 objects with properties, 14 id-shaped props.
    for key, what in (("refs", "a $ref"), ("objects", "an object with `properties`"),
                      ("bigints", "an id-shaped property")):
        if subjects[key] == 0:
            print(f"game-wire-lint: error: {len(docs)} schema(s) scanned and NOT ONE contains "
                  f"{what}. That rule has no subject, so its silence is not coherence.",
                  file=sys.stderr)
            return 2

    # ── SHRINK ARM (GT-F5) on STRING_ID_REFS. Each entry is a carve-out: a
    # `$ref` containing it satisfies CWC-A2. An entry no schema references
    # exempts nothing and stands ready to exempt the next type that takes the
    # name. Measured: all four are live.
    for r in sorted(set(string_id_refs) - id_refs_used):
        findings.append(
            f"STRING_ID_REFS entry {r!r} is referenced by no schema — it exempts nothing "
            f"today and would exempt any future $ref containing that name.")

    print(f"game-wire-lint: scanned {len(docs)} schema file(s) under {root} "
          f"({subjects['refs']} $ref, {subjects['objects']} object(s), "
          f"{subjects['bigints']} id-shaped prop(s), {subjects['enums']} enum(s))")
    for f in findings:
        print(f)
    if findings:
        print(f"\ngame-wire-lint: FAIL — {len(findings)} finding(s)")
        return 1
    print("game-wire-lint: OK — schemas coherent "
          "(refs resolve · ids are strings · objects closed)")
    return 0


# ── SELF-TEST ────────────────────────────────────────────────────────────────
import json as _json  # noqa: E402


def _schema(props: dict | None = None, drop: tuple = (), **over) -> str:
    """Build a fixture by mutating the DICT, never by string-replacing the JSON.

    The first draft of these cases did `_schema().replace('"actor_id": {...}', ...)`
    on the serialised text — and `json.dumps(indent=2)` puts every key on its own
    line, so not one of those replacements matched. Four probes silently tested
    the UNMODIFIED schema and reported ok. That is `GTD-19`'s trap (`str.replace`
    returns the original on no match) inside the fixtures of a gate about claims
    with nothing behind them.
    """
    doc = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://loreweave.dev/game-wire/a.schema.json",
        "$defs": {"Uint64String": {"type": "string"},
                  "EntityId": {"type": "string"},
                  "Uuid": {"type": "string"},
                  "Digest": {"type": "string"}},
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "turn_number": {"$ref": "#/$defs/Uint64String"},
            "actor_id": {"$ref": "#/$defs/EntityId"},
            "trace_id": {"$ref": "#/$defs/Uuid"},
            "body_digest": {"$ref": "#/$defs/Digest"},
            "kind": {"type": "string", "enum": ["a", "b"]},
            # KEEPERS. Every STRING_ID_REFS entry must stay referenced no matter
            # what a probe overrides, or the shrink arm reds and the probe passes
            # on THAT instead of on the rule it names — which is what happened to
            # four bigint arms before these existed. The names are deliberately
            # not id-shaped, so they are invisible to the CWC-A2 rule.
            "keep_u64": {"$ref": "#/$defs/Uint64String"},
            "keep_entity": {"$ref": "#/$defs/EntityId"},
            "keep_uuid": {"$ref": "#/$defs/Uuid"},
            "keep_digest": {"$ref": "#/$defs/Digest"},
        },
    }
    if props:
        doc["properties"].update(props)
    for k in drop:
        doc.pop(k, None)
    doc.update(over)
    return _json.dumps(doc, indent=2)


def self_test() -> int:
    import contextlib
    import io
    import tempfile

    failures = 0

    def probe(name: str, want: int, files, *, string_id_refs=None, no_dir=False):
        nonlocal failures
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "game-wire")
            if not no_dir:
                os.makedirs(root, exist_ok=True)
                for fn, body in files.items():
                    with open(os.path.join(root, fn), "w", encoding="utf-8") as fh:
                        fh.write(body)
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    got = check(root, STRING_ID_REFS if string_id_refs is None
                                else string_id_refs)
            except SystemExit as e:  # noqa: BLE001 - die() must not survive
                failures += 1
                print(f"  FAIL {name}: called sys.exit({e.code}) — it must return a code")
                return
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e}")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    OK = {"a.schema.json": _schema()}
    print("game-wire-lint --self-test")

    probe("a coherent schema passes", 0, OK)

    # json
    probe("invalid JSON fails", 1, {"a.schema.json": _schema(), "b.schema.json": "{oops"})
    probe("a missing $schema fails", 1, {"a.schema.json": _schema(drop=("$schema",))})
    probe("a missing $id fails", 1, {"a.schema.json": _schema(drop=("$id",))})

    # refs
    # A NON-id-shaped property: pointing `trace_id` at a bad ref also trips the
    # CWC-A2 rule (a *_id whose $ref names no string carrier), so the probe would
    # pass on that rather than on ref resolution.
    probe("an unresolvable $ref fails", 1, {
        "a.schema.json": _schema({"payload": {"$ref": "#/$defs/Nope"}})})

    # bigint — CWC-A2
    probe("an id-shaped property typed as a NUMBER fails", 1, {
        "a.schema.json": _schema({"actor_id": {"type": "integer"}})})
    probe("...and turn_number as a number fails", 1, {
        "a.schema.json": _schema({"turn_number": {"type": "integer"}})})
    probe("...but a plain string is fine", 0, {
        "a.schema.json": _schema({"actor_id": {"type": "string"}})})
    # THE NARROWED CARVE-OUT
    probe("an id-shaped property typed `object` fails (only from_tokens may be)", 1, {
        "a.schema.json": _schema({"actor_id": {"type": "object"}})})
    probe("...but from_tokens as an object is allowed", 0, {
        "a.schema.json": _schema({"from_tokens": {"type": "object"}})})

    # closed
    probe("an object without additionalProperties:false fails", 1, {
        "a.schema.json": _schema(drop=("additionalProperties",))})
    probe("an enum without an explicit type fails", 1, {
        "a.schema.json": _schema({"kind": {"enum": ["a", "b"]}})})

    # the shrink arm
    probe("a STRING_ID_REFS entry no schema references fails", 1, OK,
          string_id_refs=("Uint64String", "EntityId", "Uuid", "Digest", "GhostId"))

    # floors
    probe("a MISSING directory is misuse, not a pass", 2, {}, no_dir=True)
    probe("a directory with NO schema files is misuse", 2, {})
    probe("schemas with no $ref at all is misuse", 2, {
        "a.schema.json": _json.dumps({
            "$schema": "x", "$id": "y", "type": "object",
            "additionalProperties": False,
            "properties": {"actor_id": {"type": "string"}}})})

    if failures:
        print(f"game-wire-lint --self-test: {failures} rule(s) did not behave")
        return 2
    print("game-wire-lint --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="game-wire-lint.py")
    ap.add_argument("--path", default=DEFAULT_DIR, help="contracts/game-wire dir")
    ap.add_argument("--self-test", "--selftest", dest="self_test", action="store_true",
                    help="prove every rule bites, over synthetic schemas")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    rc = self_test()
    if rc:
        return rc
    print()
    return check(args.path)


if __name__ == "__main__":
    sys.exit(main())
