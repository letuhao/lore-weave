#!/usr/bin/env python3
"""orphan-model-gate — a projection with no PRODUCER is a dead end, not a feature.

THE DEFECT THIS EXISTS TO PREVENT
---------------------------------
Measured 2026-08-04, and it had been true since 2026-05-29:

    $ grep -rn '"pc.created"' --include=*.rs crates/ services/
    projection-reference/src/lib.rs   (a declaration table)
    projections/pc/src/lib.rs         (the projector, and its own unit test)
    world-service/benches/…           (a bench fixture)
    world-service/tests/…             (tests)

    production code emitting it: NONE

Seven of the ten L3.A projection tables could only ever be rebuilt from events
that nothing wrote. They had a projector, a table, a rebuilder, a golden
fixture, an independent oracle and a benchmark — everything except an input.
`0017` removed them.

**The failure was not writing them. It was never asking.** A round designed the
actor hub without auditing what already claimed to model an actor, so a
pre-`D-2` vocabulary model (`name`, `stats JSONB`, a hardcoded status set) sat in
the per-reality schema with a `// TODO(cycle 17+ L4): pc.stats_changed` beside
it — an invitation to make it a second SSOT for an actor's numbers.

THE RULE
--------
Every event type a projector HANDLES must be PRODUCED by non-test, non-fixture
source somewhere in the repo — or be listed in `KNOWN_UNPRODUCED` with a reason.

WHAT COUNTS AS A PRODUCER
-------------------------
A string literal naming the event type, in a `.rs` / `.ts` / `.go` file that is
NOT a test, a bench, a fixture, an example, or a declaration table. The
declaration tables are excluded BY PATH because they are the thing that would
otherwise vouch for themselves: `projection-reference` exists to say which
events target which tables, so counting it as a producer would make every
declared event self-justifying — the exact circularity `D-446` found when a
witness table counted as its own witness.

WHY A LIST RATHER THAN A CLEAN SWEEP
------------------------------------
An event can legitimately have no producer yet: the writer lands in a later
slice. That is a NORMAL state, and a gate that forbade it would cry wolf on
every half-built vertical. What is NOT normal is nobody noticing for two
months. So an unproduced event must be NAMED, with a reason, and the list
shrinks — a name that becomes produced FAILS, which is what forces the deletion.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SEARCH_ROOTS = ("crates", "services")
SOURCE_SUFFIXES = (".rs", ".ts", ".go")

# Paths whose event-type literals are NOT evidence of a producer.
NON_PRODUCER_PARTS = (
    "/tests/", "/benches/", "/examples/", "/fixtures/", "node_modules",
    "/target/", "/projection-reference/", "/projection-golden/",
)

HANDLER_RE = re.compile(r'"(?P<ev>[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*)"\s*=>')
LITERAL_RE = re.compile(r'"(?P<ev>[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*)"')

# An event a projector handles that nothing produces YET. Each needs a reason,
# and the list must SHRINK: a name here that becomes produced is a finding, so a
# slice that lands its writer is forced to delete its own row.
KNOWN_UNPRODUCED: dict[str, str] = {
    # ── found by this gate on its FIRST run, 2026-08-04 ──────────────────
    # The pc/npc removal was scoped by the PO to pc/npc. This gate then
    # measured that FIVE MORE handled events have no producer either — every
    # surviving projector except `canon`, whose events `world-service`'s
    # reality_seeder really does emit. They are NAMED rather than deleted,
    # because naming was the missing step: the pc/npc pair sat unproduced for
    # two months precisely because nothing said so out loud.
    "region.created": "region aggregate has no writer yet; the projector predates it "
                      "(raid-c13, 2026-05-29). Delete or land the writer — do not leave silent",
    "region.ambient_changed": "same as region.created",
    "session.participant_joined": "session aggregate has no writer yet; same shape",
    "session.participant_left": "same as session.participant_joined",
    "world.kv_unset": "`world.kv_set` IS produced; its unset twin is not — half a "
                      "vertical, which is the normal state the list exists to make visible",
}


class Finding:
    def __init__(self, event: str, handler: str, why: str):
        self.event, self.handler, self.why = event, handler, why

    def __str__(self) -> str:
        return f"  `{self.event}` handled by {self.handler} — {self.why}"


def _source_files() -> list[Path]:
    out: list[Path] = []
    for root in SEARCH_ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.suffix in SOURCE_SUFFIXES and p.is_file():
                out.append(p)
    return sorted(out)


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("\\", "/")


def _is_producer_path(rel: str) -> bool:
    return not any(part in f"/{rel}" for part in NON_PRODUCER_PARTS)


def scan(files: list[Path], known: dict[str, str] | None = None) -> list[Finding]:
    # `known` is injectable so the self-test can drive the rule with its OWN
    # registry. Reading the module constant from a case would make every case
    # depend on the shipped tree's rows — which is how the first version failed
    # four cases the moment the registry gained an entry.
    known = KNOWN_UNPRODUCED if known is None else known
    handled: dict[str, str] = {}
    produced: set[str] = set()

    for p in files:
        rel = _rel(p)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # A projector is any file under crates/projections/.
        if "/projections/" in f"/{rel}":
            for m in HANDLER_RE.finditer(text):
                handled.setdefault(m.group("ev"), rel)
        if _is_producer_path(rel) and "/projections/" not in f"/{rel}":
            for m in LITERAL_RE.finditer(text):
                produced.add(m.group("ev"))

    out: list[Finding] = []
    for ev, where in sorted(handled.items()):
        if ev in produced:
            continue
        if ev in known:
            continue
        out.append(Finding(ev, where, "no production code emits it — a projector with no input"))

    # ...and the list must SHRINK FROM BOTH ENDS.
    #
    # A row whose event became PRODUCED has done its job. A row whose event is
    # no longer HANDLED BY ANYTHING has outlived its subject — `session.started`
    # and `session.ended` were in exactly that state within an hour of the list
    # being written, because `0017` deleted the only projector that handled
    # them. A registry that can only grow stops being read.
    for ev, reason in sorted(known.items()):
        if ev not in handled:
            out.append(Finding(
                ev, "KNOWN_UNPRODUCED",
                f"no projector handles it any more — the row outlived its subject "
                f"(reason on file: {reason})"))
        elif ev in produced:
            out.append(Finding(
                ev, "KNOWN_UNPRODUCED",
                f"is produced now — delete its row (reason on file: {reason})"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true", help="prove the rule bites")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    files = _source_files()
    findings = scan(files)
    if findings:
        print(f"orphan-model-gate: {len(findings)} finding(s)\n")
        for f in findings:
            print(f)
        print(
            "\nA projector with no producer is machinery with no input: it can only ever\n"
            "be rebuilt from events nothing wrote. Seven of ten L3.A tables were in that\n"
            "state for two months (`0017`). Either land the producer, or delete the\n"
            "projector — or add a KNOWN_UNPRODUCED row WITH A REASON if the writer is a\n"
            "later slice."
        )
        return 1
    print(f"orphan-model-gate: OK — every handled event has a producer "
          f"({len(KNOWN_UNPRODUCED)} named as not-yet-produced) across {len(files)} source file(s)")
    return 0


# ── non-vacuity ──────────────────────────────────────────────────────────────

def self_test() -> int:
    failures = 0

    def case(label: str, cond: bool) -> None:
        nonlocal failures
        if cond:
            print(f"  ok   {label}")
        else:
            failures += 1
            print(f"  FAIL {label}")

    import tempfile
    import os

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        proj = root / "crates" / "projections" / "probe"
        proj.mkdir(parents=True)
        (proj / "lib.rs").write_text('match e { "probe.made" => vec![], _ => vec![] }',
                                     encoding="utf-8")
        svc = root / "services" / "probe-service" / "src"
        svc.mkdir(parents=True)

        global REPO
        real_repo = REPO
        try:
            REPO = root
            # 1. handled, nothing produces it -> reported
            case("a projector with no producer is reported",
                 len(scan(_source_files(), known={})) == 1)

            # 2. a TEST is not a producer
            tests = root / "services" / "probe-service" / "tests"
            tests.mkdir(parents=True)
            (tests / "t.rs").write_text('let x = "probe.made";', encoding="utf-8")
            case("a test literal does not count as a producer",
                 len(scan(_source_files(), known={})) == 1)

            # 3. the DECLARATION TABLE is not a producer either — it would
            #    otherwise vouch for every event it declares (`D-446`).
            decl = root / "crates" / "projection-reference" / "src"
            decl.mkdir(parents=True)
            (decl / "lib.rs").write_text('"probe.made" => &[("t", Kind::Insert)],',
                                         encoding="utf-8")
            case("the declaration table does not vouch for itself",
                 len(scan(_source_files(), known={})) == 1)

            # 4. real production source -> silent
            (svc / "main.rs").write_text('emit("probe.made");', encoding="utf-8")
            case("a production literal clears it",
                 len(scan(_source_files(), known={})) == 0)
            # ...and a row that outlived its subject is a finding, so the
            # registry shrinks from both ends.
            case("a row nothing handles any more is reported",
                 len(scan(_source_files(), known={"gone.event": "stale"})) == 1)
        finally:
            REPO = real_repo

    # 5. the shipped tree must be silent, or the gate cries wolf
    shipped = scan(_source_files())
    if shipped:
        failures += 1
        print(f"  FAIL the shipped tree reports {len(shipped)} finding(s) — cry wolf")
        for f in shipped:
            print(f"       {f}")
    else:
        print("  ok   the shipped tree reports nothing, so the rule does not cry wolf")

    # 6. ...and it must have a SUBJECT, or that silence means nothing.
    handled_total = 0
    for p in _source_files():
        rel = _rel(p)
        if "/projections/" in f"/{rel}":
            handled_total += len(set(HANDLER_RE.findall(
                p.read_text(encoding="utf-8", errors="replace"))))
    if handled_total == 0:
        failures += 1
        print("  FAIL no projector handles any event — the gate has no subject")
    else:
        print(f"  ok   the gate has a subject: {handled_total} handled event type(s)")

    if failures:
        print(f"\norphan-model-gate --self-test: {failures} rule(s) did not behave")
        return 1
    print("\norphan-model-gate --self-test: every rule bites, and none cries wolf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
