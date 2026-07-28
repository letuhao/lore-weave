#!/usr/bin/env python3
"""envelope-mirror-gate — the Go and Rust event envelopes must not drift apart.

THE GAP THIS CLOSES
-------------------
`contracts/events/envelope.go` is the SSOT for the cross-service event envelope,
and `crates/dp-kernel/src/envelope.rs` is its Rust mirror. Both files SAY so:

    //! `EventEnvelope` — Rust mirror of `contracts/events/envelope.go`
    //! Adding/removing/renaming a field here REQUIRES a paired change to the
    //! Go envelope.

    // The envelope is INTENTIONALLY identical in Go + Rust — having a single
    // shape makes upcasters / validators / projectors language-portable.

**And nothing checked it.** A rule with no gate is a rule that decays; this
repo's whole meta-pattern is rule + SoT + gate + test, and this pair had three
of the four. The failure it permits is the classic polyglot one: a Go producer
writes a field, the Rust projector deserializes without it and silently drops
it — `serde` does not error on unknown fields by default, and Go does not error
on missing ones. No test fails. The data is simply gone downstream.

It became worth building the moment migration 0016 added `ruleset_digest` to
both sides: extending an unguarded mirror without adding the guard would have
repeated exactly the mistake being fixed.

WHAT IT CHECKS
--------------
The JSON field names on both sides must be the same SET, in the same ORDER:

  missing-in-rust   a Go `json:"x"` tag with no Rust counterpart
  missing-in-go     a Rust serde field with no Go counterpart
  order-drift       both sides have the field, at different positions

Order matters because the two structs are documented as "identical", and a
reader comparing them field-by-field is the only review this contract gets.

WHAT IT DELIBERATELY DOES NOT CHECK
-----------------------------------
Types. `uuid.UUID`/`Uuid`, `time.Time`/`String`, `map[string]any`/`Value` are
intentionally different spellings of the same wire shape, and encoding a
Go-type-to-Rust-type table here would be a second contract to keep in sync — a
gate that needs its own gate. Names and order catch the drift that actually
happens (a field added on one side only); types are a review concern.

SELF-TEST
---------
`--self-test` runs the checker against fixtures with a dropped field and a
reordered field, and fails if either goes unreported.

Usage:
    python scripts/envelope-mirror-gate.py
    python scripts/envelope-mirror-gate.py --self-test
"""

from __future__ import annotations

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GO_FILE = "contracts/events/envelope.go"
RS_FILE = "crates/dp-kernel/src/envelope.rs"

GO_STRUCT = re.compile(r"type\s+Envelope\s+struct\s*\{(.*?)\n\}", re.S)
GO_TAG = re.compile(r'json:"([A-Za-z0-9_]+)')

RS_STRUCT = re.compile(r"pub\s+struct\s+EventEnvelope\s*\{(.*?)\n\}", re.S)
RS_FIELD = re.compile(r"^\s*pub\s+([A-Za-z0-9_]+)\s*:", re.M)
RS_RENAME = re.compile(r'#\[serde\(\s*rename\s*=\s*"([A-Za-z0-9_]+)"')


def go_fields(src: str) -> list[str]:
    m = GO_STRUCT.search(src)
    if not m:
        return []
    out = []
    for line in m.group(1).split("\n"):
        if line.strip().startswith("//"):
            continue
        tag = GO_TAG.search(line)
        if tag:
            out.append(tag.group(1))
    return out


def rust_fields(src: str) -> list[str]:
    m = RS_STRUCT.search(src)
    if not m:
        return []
    body = m.group(1)
    out = []
    # A `#[serde(rename = "…")]` on the line(s) above wins over the ident.
    pending_rename: str | None = None
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith("///") or stripped.startswith("//"):
            continue
        r = RS_RENAME.search(line)
        if r:
            pending_rename = r.group(1)
            continue
        f = RS_FIELD.match(line)
        if f:
            out.append(pending_rename or f.group(1))
            pending_rename = None
    return out


def check(go_src: str, rs_src: str) -> list[str]:
    g, r = go_fields(go_src), rust_fields(rs_src)
    findings: list[str] = []
    if not g:
        findings.append("could not parse `type Envelope struct` in the Go SSOT")
    if not r:
        findings.append("could not parse `pub struct EventEnvelope` in the Rust mirror")
    if not g or not r:
        return findings

    for name in g:
        if name not in r:
            findings.append(
                f"missing-in-rust: Go declares `{name}` and the Rust mirror does not — "
                "a Go producer writing it would be silently dropped by every Rust consumer"
            )
    for name in r:
        if name not in g:
            findings.append(
                f"missing-in-go: the Rust mirror declares `{name}` and the Go SSOT does not — "
                "the SSOT is the Go file, so either add it there or remove it here"
            )
    if sorted(g) == sorted(r) and g != r:
        findings.append(
            f"order-drift: same fields, different order.\n"
            f"      go:   {g}\n"
            f"      rust: {r}\n"
            "      The two structs are documented as identical; field order is the only "
            "thing a human comparing them side by side can actually rely on."
        )
    return findings


GO_FIXTURE = """
type Envelope struct {
\tEventID   uuid.UUID `json:"event_id"`
\tEventType string    `json:"event_type"`
\tPayload   any       `json:"payload"`
}
"""
RS_OK = """
pub struct EventEnvelope {
    pub event_id: Uuid,
    pub event_type: String,
    pub payload: Value,
}
"""
RS_DROPPED = """
pub struct EventEnvelope {
    pub event_id: Uuid,
    pub payload: Value,
}
"""
RS_REORDERED = """
pub struct EventEnvelope {
    pub event_type: String,
    pub event_id: Uuid,
    pub payload: Value,
}
"""


def self_test() -> int:
    ok = True
    if check(GO_FIXTURE, RS_OK):
        print("SELF-TEST FAIL: a matching pair was reported")
        ok = False
    if not any("missing-in-rust" in f for f in check(GO_FIXTURE, RS_DROPPED)):
        print("SELF-TEST FAIL: a field missing from the Rust mirror was not reported")
        ok = False
    if not any("order-drift" in f for f in check(GO_FIXTURE, RS_REORDERED)):
        print("SELF-TEST FAIL: a reordered field was not reported")
        ok = False
    if ok:
        print("self-test: the gate bites (dropped field + reordered field detected; "
              "a matching pair is silent)")
        return 0
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true",
                    help="prove the gate can fail, then exit")
    ap.add_argument("--staged", action="store_true",
                    help="pre-commit mode: run only when either side is staged")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.staged:
        import subprocess
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=REPO_ROOT, capture_output=True, text=True).stdout
        touched = {p.strip().replace("\\", "/") for p in out.split("\n")}
        if GO_FILE not in touched and RS_FILE not in touched:
            return 0

    try:
        go_src = open(os.path.join(REPO_ROOT, GO_FILE), encoding="utf-8").read()
        rs_src = open(os.path.join(REPO_ROOT, RS_FILE), encoding="utf-8").read()
    except OSError as e:
        print(f"envelope-mirror-gate: cannot read a side: {e}")
        return 1

    findings = check(go_src, rs_src)
    print(f"envelope-mirror-gate: {GO_FILE} vs {RS_FILE}")
    for f in findings:
        print(f"  [envelope-drift] {f}")
    if findings:
        print(f"\nenvelope-mirror-gate: FAIL — {len(findings)} finding(s)")
        print("The envelope is ONE shape in two languages. Change both sides together.")
        return 1
    print(f"envelope-mirror-gate: OK — {len(go_fields(go_src))} field(s) agree, in order")
    return 0


if __name__ == "__main__":
    sys.exit(main())
