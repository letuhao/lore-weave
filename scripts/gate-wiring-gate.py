#!/usr/bin/env python3
"""gate-wiring-gate — a gate nobody runs is not a gate.

THE FINDING THIS EXISTS TO PREVENT (2026-07-29) — AND THE CORRECTION TO IT
--------------------------------------------------------------------------
The first pass of this audit reported **26 of 58** gate scripts "running
nowhere". **That number was wrong, and the mistake is worth keeping here**
because it is the same mistake the gate exists to catch, made while writing it:
`.github/workflows/lint-foundation.yml` drives its lints as **matrices of bare
names** —

    matrix:
      lint:
        - raw-sql-lint
        - language-bias-gate

— and a path-only substring search saw none of them. Corrected, the true figure
is **3** genuinely unwired (`raid/post-raid-review-gate.sh`,
`raid/prod-isolation-lint.sh`, `workflow-gate.sh`).

**The real rot was worse than "unwired", and CI had been saying so out loud.**
Six legs of `lint-foundation` have failed on **`main`** since at least
2026-07-26 — `raw-sql-lint`, `injection-coverage-lint`, `language-bias-gate`,
`pagination-cap-lint`, `dep-pinning-lint`, `capacity-budget-lint`. They are not
advisory: `continue-on-error` appears in that workflow only inside a comment
recording that it was deliberately removed "to give the standards teeth". The
gates ran, blocked, and reported — and six consecutive red runs were ignored.

    A gate nobody runs is not a gate.
    A red gate nobody acts on is worse: it trains everyone to ignore the colour.

So this file does two jobs. The wiring check answers *"is every gate reachable?"*
— cheap, hook-able, and it found the three. `--run-all` + `KNOWN_RED` answers the
harder one: **every failure is either fixed or has a tracked deferral against its
name**, and a `KNOWN_RED` row that turns green FAILS, so the list shrinks instead
of quietly becoming the new normal.

It is the mechanical answer to docs/standards/non-vacuity.md row 19 — the
degenerate case of NV-3, where the scope never reaches the check because nobody
looks at the result.

SCOPE — WHAT IS IN, AND THE LIMIT SAID OUT LOUD
-----------------------------------------------
IN: files whose name ends `-gate` / `-lint` / `-live-smoke` (either separator).

⚠️ **The `-live-smoke` half was added on 2026-08-30 (L4), against what this
section used to say** — and the argument it used to make was contradicted by
this same file, twenty lines further down. It read: *"pulling them in would
produce nine SKIP lines and no signal"*. But `NEEDS_STACK`'s own comment says
the opposite about exactly those lines — *"Printed, never silent. A skipped gate
that says nothing is indistinguishable from a passing one, and that is the exact
confusion this file exists to remove."* Both cannot be right. A SKIP carrying a
reason IS signal; **absence** is the thing that carries none, and fifteen live
smokes were absent.

The count was stale too: nine when written, fifteen when measured.

What this does **not** do is put them in CI. They still cannot run on a bare
checkout, `D-PUBLISHER-SMOKE-NOT-IN-CI` and `D-META-LIVE-SMOKE-NOT-IN-CI` are
untouched, and a stack-up CI job is still the thing that would discharge them.
This changes *invisible* to *skipped, with a reason, by name* — which is worth
having on its own and is not a claim to have solved the other problem.

SCOPE IS A PREDICATE, NOT A LIST
--------------------------------
`is_gate()` matches on the FILENAME SHAPE, so a gate written tomorrow is covered
the day it is created. An enumerated registry would be default-uncovered — the
exact mistake this repo has now made enough times to have a standard about it.

The consequence, deliberately: **adding `scripts/foo-gate.py` fails this gate**
until it is wired or exempted. That friction is the product.

THREE WAYS TO SATISFY IT
------------------------
1. referenced by name in `.githooks/pre-commit`
2. referenced by name in any `.github/workflows/*.yml`
3. an `EXEMPT` row here, carrying a REASON

…and one way to be honest about a gate that is wired but currently failing:
a `KNOWN_RED` row, which must name a tracked deferral. `--run-all` treats those
as expected-red **and fails if one turns GREEN**, so the list shrinks when the
debt is paid instead of becoming permanent. That is the same discipline
`file-ceiling-gate` applies to allowlisted line counts.

    python scripts/gate-wiring-gate.py             # wiring check (fast)
    python scripts/gate-wiring-gate.py --run-all   # execute every gate (CI)
    python scripts/gate-wiring-gate.py --self-test
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
HOOK = REPO / ".githooks" / "pre-commit"
WORKFLOWS = REPO / ".github" / "workflows"


def is_gate(name: str) -> bool:
    """Filename shape, so tomorrow's gate is in scope the day it is written."""
    if not name.endswith((".py", ".sh")):
        return False
    stem = name.rsplit(".", 1)[0]
    # BOTH separators. The repo writes gates kebab-case (`ai-provider-gate.py`)
    # and pytest files snake_case (`test_tier_tag_gate.py`), and accepting only
    # `-` would let a `foo_gate.py` written tomorrow slip the scope — the same
    # default-uncovered shape this file exists to close. Accepting `_` pulls the
    # pytest self-tests in too; they get EXEMPT rows, which is the visible
    # outcome rather than the silent one.
    # 🔴 `-live-smoke` (L4, 2026-08-30). A live smoke is not a gate — it needs a running
    # stack and can never be a CI leg — but it IS a check somebody wrote and expects to
    # protect something, which is exactly what this file exists to keep visible.
    #
    # Measured before widening: FIFTEEN of them, in `scripts/` and `scripts/raid/`, and this
    # predicate matched NONE. Every one was invisible here — not exempt, not tracked-red,
    # not skipped-with-a-reason: absent. `picker-search-live-smoke.sh` was only the fifteenth
    # to arrive, so the row that sent me here ("a smoke I shipped that nothing runs") was
    # describing a category, not a mistake in one commit.
    #
    # They land in NEEDS_STACK, so `--run-all` prints `SKIP … needs a live stack: <reason>`
    # for each. That is the point: a check that says nothing is indistinguishable from a
    # passing one, and fifteen of them were saying nothing.
    return (
        stem.endswith(("-gate", "_gate", "-lint", "_lint",
                       "-live-smoke", "_live_smoke"))
        or "-lint-" in stem
        or "_lint_" in stem
        or "-gate-" in stem
        or "_gate_" in stem
    )


# name -> reason. NOT a place to park an unwired gate: every row here says why
# the file is not a gate at all, or why running it on a hook/CI is wrong.
EXEMPT: dict[str, str] = {
    "scripts/test_ai_provider_gate.py": "pytest self-test OF ai-provider-gate; runs with the python suite",
    "scripts/test_tier_tag_gate.py": "pytest self-test OF tier-tag-gate; runs with the python suite",
    "scripts/workflow-gate.py": "the WORKFLOW state machine, invoked explicitly by /loom and by the "
                        "pre-commit hook's phase check — not a code gate over the tree",
    "scripts/workflow-gate.sh": "a thin wrapper around workflow-gate.py (which is exempt for "
                        "the same reason): it takes a SUBCOMMAND and prints usage with rc=1 "
                        "when given none, so there is nothing for a tree-scan to run",
    "scripts/raid/post-raid-review-gate.sh": "a per-CYCLE checklist gate — it demands a "
                        "specific dated plan file (docs/plans/2026-06-13-…) and is invoked by "
                        "the RAID protocol at a cycle boundary, not over the tree",
    "scripts/gate-wiring-gate.py": "this file. It is not exempt from RUNNING — the hook and CI "
                           "both invoke it by name, and the self-test asserts exactly that "
                           "rather than trusting this sentence. The row exists only so "
                           "`--run-all` does not recurse into itself",
}

# Gates that need a LIVE STACK (docker, Postgres, a built binary). `--run-all`
# SKIPS these and says so on every run — a skip that prints is a known hole; a
# skip that is silent is a gate reported as passing when it never ran, which is
# the failure this whole file is about. They belong in a stack-up CI job.
NEEDS_STACK: dict[str, str] = {
    "scripts/standing-integrity-gate-smoke.sh": "brings up foundation-dev postgres + needs "
        "replay-aggregate and integrity-checker binaries built first",
    "scripts/perf/bencher-gate.sh": "a benchmark comparison; needs a baseline run to compare "
        "against, and a shared runner makes the numbers meaningless",
    "scripts/perf/bench-gate.sh": "same family — needs a built target and a recorded baseline, "
        "neither of which a tree-scan has",
    "scripts/perf/rust-bench-gate.sh": "needs cargo AND a criterion baseline; reports "
        "NOTRUN(setup) without them, which is not a verdict",

    # These three fail IDENTICALLY with `KeyError: JWT_SECRET` at import: they
    # import service code that reads env at module level, so they need a
    # configured environment rather than a checkout. Classified NEEDS_STACK
    # rather than KNOWN_RED because KNOWN_RED means "a real finding is waiting";
    # these are harnesses that never started. Making them runnable in CI with an
    # injected dummy secret is tracked as D-GATE-ROT-ENV-AT-IMPORT.
    "scripts/context-inspector-trace-gate.py": "imports service code reading JWT_SECRET at "
        "import time — needs env, not just a checkout (D-GATE-ROT-ENV-AT-IMPORT)",
    "scripts/eval/run_quality_gate.py": "an EVAL harness against a live service; same "
        "JWT_SECRET-at-import (D-GATE-ROT-ENV-AT-IMPORT)",
    "scripts/eval/run_skill_gate.py": "an EVAL harness against a live service; same "
        "JWT_SECRET-at-import (D-GATE-ROT-ENV-AT-IMPORT)",

    # ── the live smokes (L4, 2026-08-30) ────────────────────────────────────────────────
    # Fifteen checks that were invisible to this file until `is_gate` learned the shape.
    # Every one needs a RUNNING stack by definition, so NEEDS_STACK is the honest category
    # rather than a parking space: none of them can ever be a CI leg on a bare checkout, and
    # saying that once here is better than fifteen people rediscovering it.
    #
    # The reasons are each script's OWN, read out of its header — a boilerplate "needs a
    # stack" fifteen times would be a row that carries no information and rots without
    # anybody noticing.
    "scripts/archive-worker-live-smoke.sh": "stands up foundation-dev and runs the "
        "archive-worker against it (P1 DEFERRED 056+057)",
    "scripts/bitemporal-window-live-smoke.py": "asks a RUNNING knowledge-service whether a "
        "windowed read holds a reader at a position; T48s found live that it did not",
    "scripts/entity-lifecycle-guards-live-smoke.sh": "proves the three Phase-0 lifecycle "
        "guards on a running glossary-service (QC-0)",
    "scripts/epoch-activation-live-smoke.sh": "drives the epoch path end to end against a "
        "real Postgres (Q0b B3b+B3c)",
    "scripts/glossary-lifecycle-live-smoke.sh": "the QC-4 emit-wiring proof; it catches a "
        "BYPASS, which only exists at runtime",
    "scripts/kal-auth-boundary-live-smoke.py": "asks whether the KAL's guard DISCRIMINATES "
        "rather than merely answers — needs the KAL up and a real token",
    "scripts/kal-read-surface-live-smoke.py": "drives every KAL read route, derived from the "
        "controller, and reports which ANSWER",
    "scripts/knowledge-graph-backend-live-smoke.py": "proves the knowledge HTTP surface on "
        "whichever engine KNOWLEDGE_GRAPH_BACKEND selected; it writes, so it needs a stack",
    "scripts/meta-rs-pg-live-smoke.sh": "runs crates/meta-rs/tests/pg_live.rs against a real "
        "Postgres (Q1 B2b)",
    "scripts/metaworker-live-smoke.sh": "stands up TWO databases for the meta-worker canon "
        "fan-out (P1 DEFERRED 069)",
    "scripts/picker-search-live-smoke.sh": "rebuilt images plus a browser: it asserts the "
        "picker's typed term reaches the SERVER, which a client-side filter renders "
        "identically (L4)",
    "scripts/publisher-live-smoke.sh": "the event-sourcing spine's publisher wiring "
        "(DEFERRED 054 D-PUBLISHER-LIVE-WIRING)",
    "scripts/raid/degraded-live-smoke.sh": "orchestrates the L1.J degraded-mode flow; it "
        "brings the stack up itself (RAID cycle 33)",
    "scripts/retention-worker-live-smoke.sh": "runs both retention paths against live data "
        "(P1 DEFERRED 058)",
    "scripts/state-asof-live-smoke.sh": "proves the book-wide as-of read end to end on a "
        "running stack and measures it (QC-1)",

    # L2 — a RATCHET over live data, so it needs the graph rather than a checkout.
    "scripts/event-order-collision-gate.py": "counts colliding (project_id, event_order) "
        "pairs in g_shared against a frozen ceiling; needs the AGE store, not a tree scan",

    # L1 — reports the causal pass's reach/yield/consistency over live data.
    "scripts/causal-coverage-gate.py": "measures the causal pass over g_shared and asserts "
        "every ordered edge is explained by its own window algorithm; needs the AGE store",
}

# Gates too SLOW to sit in a shared run. Skipped with the reason printed, exactly
# like NEEDS_STACK — a third category rather than a KNOWN_RED row, because
# "expensive" is not "failing" and calling it red would put a non-finding on the
# board next to two security ones.
TOO_SLOW: dict[str, str] = {
    "scripts/meta-write-discipline-lint.sh": "74s standalone on a warm cache and >900s under "
        "the shared runner — it greps every Go/Rust/SQL/TS file once PER META TABLE (33 of "
        "them), so it is quadratic in a repo this size. Wants its own CI leg, or a rewrite "
        "that walks the tree once. Tracked: D-GATE-SLOW-META-WRITE-DISCIPLINE",
}

# name -> (deferral id, why it is red). `--run-all` expects these to FAIL, and
# fails if one goes GREEN so the row gets deleted instead of outliving its debt.
# CLEARED 2026-07-29, and the rows are GONE rather than annotated: `--run-all`
# fails when a KNOWN_RED gate turns green, which is what forces the deletion.
#   raw-sql-lint          D-GATE-ROT-RAW-SQL   — false positive, but the exemption
#                         is guarded by a test that reds if the interpolated names
#                         stop being module-level literals.
#   injection-coverage    D-GATE-ROT-INJECTION — a REAL hole: chapter text, entity
#                         names and span excerpts reached an LLM judge prompt
#                         unsanitized. Fixed, and the lint tightened from
#                         "mentions the sanitizer" to "calls it".
#: Gates that WRITE to the working tree while they run. They must not share the tree with a
#: concurrent reader, so the runner executes them serially, after everything else.
#: `guard-redability-gate` injects a real violation into real source and restores it from saved
#: bytes; that is its mechanism, not a bug, and the isolation belongs to the RUNNER.
MUTATES_TREE: frozenset[str] = frozenset({
    "scripts/guard-redability-gate.py",
})

KNOWN_RED: dict[str, tuple[str, str]] = {
    # EMPTY, and that is the point: this list SHRINKS. `--run-all` fails when a row's gate
    # turns green, which is what forces the deletion instead of letting an acknowledgement
    # quietly become a permanent exemption.
    #
    # Last row removed 2026-08-03: `scripts/language-bias-gate.py` / D-GATE-ROT-LANGUAGE-BIAS.
    # It went green legitimately at e84214cc5 (16 offenders FIXED, 3 baselined with a stated
    # reason, 0 new) — the gate had been failing on 19 NEW offenders stacked on its 41-row
    # baseline, so a fresh violation was indistinguishable from the backlog. The remaining
    # analysis it carried (4 classes, two of which change bytes already persisted — a digest
    # input and casefold() as an identity key, so both are migrations rather than edits) lives
    # in the game-tier SESSION_HANDOFF's deferral table, which is its home. Nothing was lost
    # by deleting the row; leaving it would have failed this gate forever.
}


def discovered() -> list[str]:
    """Repo-relative paths, NOT bare names.

    `rglob` walks subdirectories — `scripts/raid/`, `scripts/perf/`,
    `scripts/eval/` all hold gates — and the first draft keyed everything on
    `p.name`, so `--run-all` built `scripts/<name>` and could not execute a
    single nested one. Six gates would have been reported as failing for a
    reason that was this file's own bug. Paths throughout, so a gate cannot be
    misidentified by living one directory down.
    """
    return sorted(
        str(p.relative_to(REPO)).replace("\\", "/")
        for p in SCRIPTS.rglob("*")
        if p.is_file() and is_gate(p.name)
    )


def _text(paths) -> str:
    """Concatenated content with COMMENT LINES REMOVED.

    A plain substring search over the raw file counts a gate as wired when the
    only mention of it is a comment saying it is NOT. The hook contains exactly
    that sentence about `meta-write-discipline-lint.sh` (~74s, so it is CI's
    job), and a comment written with the full path would have satisfied this
    check while the gate still ran nowhere — an escape hatch that opens itself.
    Bite-proven: appending `# scripts/slo-latency-lint.py …` to the hook must
    leave that gate in the unwired list.

    Both file types here (`sh`, `yml`) comment with `#`, so dropping lines whose
    first non-space character is `#` is exact rather than heuristic.
    """
    out = []
    for p in paths:
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.append("\n".join(
            ln for ln in raw.splitlines() if not ln.lstrip().startswith("#")
        ))
    return "\n".join(out)


RUNNER = "gate-wiring-gate.py --run-all"


def runner_in_ci() -> bool:
    """Does a workflow invoke `--run-all`?

    **This is the whole coverage mechanism, and it beats naming 28 gates.** The
    runner iterates `discovered()` — the same predicate — so a gate written
    tomorrow runs in CI the day it lands, with nobody remembering to add a line.
    Enumerating names in a workflow would have been default-uncovered all over
    again, one level up.

    The pre-commit hook still names the FAST gates individually. That is a
    latency optimisation (seconds, at commit time), not the coverage story.
    """
    return RUNNER in _text(sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")))


def _is_wired(rel: str, hook: str, ci: str) -> bool:
    """Wired by PATH, or by BARE STEM as a workflow matrix entry.

    `lint-foundation.yml` drives two matrices of bare names —

        matrix:
          lint:
            - raw-sql-lint
            - language-bias-gate

    — and a path-only match called every one of them "runs nowhere". The first
    audit therefore reported **26** unwired when the true figure was smaller, and
    four gates listed as *unrun* were in fact running and FAILING in CI, which is
    a different and worse problem than not running at all.

    Bare-stem matching is safe here only because `_text` has already stripped
    comments: a stem surviving into the body of a workflow is a matrix entry or
    an invocation, not prose about one.
    """
    if rel in hook or rel in ci:
        return True
    stem = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return f"- {stem}\n" in ci or f"- {stem} " in ci


def wiring_report() -> tuple[list[str], list[str]]:
    """(uncovered, stale_rows)."""
    names = discovered()
    known = (set(EXEMPT) | set(KNOWN_RED) | set(NEEDS_STACK) | set(TOO_SLOW)
             | set(NEEDS_ARGS))
    stale = [n for n in sorted(known) if n not in names]

    if runner_in_ci():
        # Total by construction. What remains to check is that the registries
        # below are honest, which `--self-test` and `--run-all` do.
        return [], stale

    hook = _text([HOOK])
    ci = _text(sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")))
    uncovered = [
        n for n in names
        if n not in EXEMPT and n not in NEEDS_STACK and n not in TOO_SLOW
        and not _is_wired(n, hook, ci)
    ]
    return uncovered, stale


# Gates that REQUIRE an argument. `_run` invokes every gate bare, and a gate whose argparse
# declares a required mutually-exclusive group exits 2 with a usage error — which the runner
# recorded as RED. Both of these are healthy (`--selftest` is 15/15 and 18/18 respectively, and
# the pre-commit hook runs them that way and has all along), so `--run-all` carried TWO
# permanent false reds.
#
# 🔴 That is worse than it sounds, and this file already says why: *"a gate that is red and
# unacknowledged is how a whole suite becomes background noise."* A red that can never be fixed
# by fixing the code teaches a reader to skim the list, and the next REAL red arrives into an
# audience that has learned to skim.
#
# DERIVED, not remembered: probing all 77 runnable Python gates bare found exactly these two
# exiting 2 with an argparse "required" error. The rest either run bare or are already in
# NEEDS_STACK / TOO_SLOW.
NEEDS_ARGS: dict[str, tuple[list[str], str]] = {
    "scripts/qc5-acceptance-gate.py": (
        ["--selftest"], "requires --file or --selftest; the live arms need a stack and models"),
    "scripts/soak-armed-gate.py": (
        ["--selftest"], "requires --url, --file or --selftest; the live read needs /metrics"),
    "scripts/glossary-ordinal-axis-gate.py": (
        ["--selftest"],
        "requires --census or --selftest; bare it can only answer DISARMED, which exits 0 and "
        "proves nothing -- T48aq found it running green and vacuous in CI on every commit"),
}


def _run(rel: str, timeout: int = 900, bare: bool = False) -> tuple[bool, float, str]:
    # RELATIVE path + cwd=REPO, never an absolute one.
    #
    # The first draft passed `str(REPO / rel)`, which on Windows is
    # `D:\Works\…\scripts\foo.sh` — and Git Bash swallows the backslashes, so
    # every one of the 27 shell gates reported
    # `D:Workssourcelore-weave-game-foundationscriptsfoo.sh: No such file`.
    # A CI job would have shipped failing everything. Worth noting which way it
    # broke: the runner called them RED, not green. A harness bug that reports
    # success is the one that ends careers.
    extra = [] if bare else NEEDS_ARGS.get(rel, ([], ""))[0]
    cmd = ([sys.executable, rel] if rel.endswith(".py") else ["bash", rel]) + extra
    t0 = time.time()
    try:
        # stdin=DEVNULL is load-bearing. `amaw-guardrail-gate.py` is a Claude
        # Code PreToolUse HOOK that does `json.loads(sys.stdin.read())`, so
        # running it as a tree scan blocks forever — and because children share
        # the parent's stdin, ONE such gate hung a second unrelated one with it
        # (both reported TIMEOUT after 900s in a run where each takes ~1s alone).
        # It is now EXEMPT, but the guard stays: a harness that executes arbitrary
        # scripts must not be hangable by one of them, and a CI job wedged for its
        # whole timeout tells you nothing about which gate did it.
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL)
        ok, out = r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        ok, out = False, f"TIMEOUT after {timeout}s"
    return ok, time.time() - t0, out


def run_all() -> int:
    """Executed in PARALLEL, and that is not an optimisation.

    Serially this takes >20 minutes on Windows. Every gate here is an independent
    read-only scan of the working tree, so there is nothing to serialise for, and
    a gate suite people cancel is back to being decorative.

    **A measurement trap, recorded so the next person does not re-derive it.**
    Shell gates run ~10x SLOWER as a Python subprocess on Windows than from a
    shell: `admin-command-registry-lint` 38s standalone -> 484s here,
    `dep-pinning-lint` 22s -> 200s. That is a git-bash-under-subprocess artifact,
    NOT a property of the gates, and it does not happen on the Linux CI runner.
    Do not move a gate to TOO_SLOW on the strength of a Windows number alone —
    `meta-write-discipline` is there because it is quadratic (it re-greps the
    whole tree once per meta table, 33 of them), which is slow everywhere.
    """
    names = [n for n in discovered() if n not in EXEMPT]
    failures, unexpected_green = [], []

    for n in sorted(TOO_SLOW):
        if n in names:
            print(f"  {n:<44} SKIP           too slow for a shared run: {TOO_SLOW[n]}")

    for n in sorted(NEEDS_STACK):
        if n in names:
            # Printed, never silent. A skipped gate that says nothing is
            # indistinguishable from a passing one, and that is the exact
            # confusion this file exists to remove.
            print(f"  {n:<44} SKIP           needs a live stack: {NEEDS_STACK[n]}")

    runnable = [n for n in names if n not in NEEDS_STACK and n not in TOO_SLOW]

    # MUTATORS RUN ALONE, AND LAST. `guard-redability-gate` proves a guard can fail by writing a
    # real violation into real source, running the guard, and restoring the bytes. That is the
    # whole point of it — and it means that for a few milliseconds per case the working tree is
    # WRONG ON PURPOSE. Running it inside the thread pool let every other gate read those bytes.
    #
    # It produced exactly the failure you would predict and it was misread for weeks: CI
    # reported `llm-budget-ssot-gate: a row claims signal_inert on a kind that DOES respond to
    # signal` — which is, verbatim, the violation guard-redability injects into `llm_budget.py`
    # in its "S7 gate" case. Three gates flapped this way (`llm-budget-ssot-gate`, `design-lint`,
    # and guard-redability accusing ITSELF of BASELINE-RED when its baseline probe read a tree
    # another case had mid-mutation). All three pass standalone, which is why it read as a
    # local/CI divergence rather than a race.
    #
    # Keyed on a declared SET, not a name guess: a second mutating gate added tomorrow joins it
    # here, and `--self-test` asserts every name in it is a real gate.
    mutators = [n for n in runnable if n in MUTATES_TREE]
    parallel = [n for n in runnable if n not in MUTATES_TREE]
    workers = min(8, (os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        parallel_results = list(pool.map(_run, parallel))
    mutator_results = [_run(n) for n in mutators]        # serial, after the pool has drained
    runnable = parallel + mutators
    results = parallel_results + mutator_results

    for n, (ok, secs, out) in zip(runnable, results):
        expected_red = n in KNOWN_RED
        if ok and expected_red:
            unexpected_green.append(n)
            print(f"  {n:<44} GREEN  ({secs:5.1f}s)  <- KNOWN_RED row is now STALE")
        elif ok:
            print(f"  {n:<44} GREEN  ({secs:5.1f}s)")
        elif expected_red:
            print(f"  {n:<44} red    ({secs:5.1f}s)  tracked {KNOWN_RED[n][0]}")
        else:
            failures.append((n, out))
            print(f"  {n:<44} RED    ({secs:5.1f}s)")

    # A NEEDS_ARGS row that is no longer needed is standing permission for nothing, and the
    # same shape this file already refuses for KNOWN_RED. Probed rather than assumed: if the
    # gate runs clean with NO arguments, the row is stale and the next gate to acquire a
    # required argument would be silently absolved by it.
    stale_args = []
    for n in sorted(NEEDS_ARGS):
        if n not in runnable:
            continue
        bare_ok, _, _ = _run(n, timeout=120, bare=True)
        if bare_ok:
            stale_args.append(n)

    rc = 0
    if stale_args:
        print(f"\ngate-wiring-gate: {len(stale_args)} NEEDS_ARGS row(s) are STALE — "
              f"the gate runs clean with no arguments:\n")
        for n in stale_args:
            print(f"  {n}  (row says: {NEEDS_ARGS[n][1]})")
        print("\nDelete the row. A registry entry that excuses nothing still "
              "excuses the NEXT gate that lands in the same file.")
        rc = 1
    if failures:
        print(f"\ngate-wiring-gate: {len(failures)} gate(s) FAILED and are not tracked:\n")
        for n, out in failures:
            # The FIRST non-empty line is usually the gate's BANNER, not its finding — every
            # gate here opens by saying what it scanned. Printing only that told CI readers
            # "design-lint: scanned 385 .md files under …" and nothing about WHY it was red,
            # which cost a full CI round-trip per diagnosis (the real answer was one broken
            # link, on line 5475 of a file the banner never mentions). Print a bounded TAIL as
            # well: a gate's verdict is at the end, and lines that mention a path or a finding
            # keyword are the ones a reader can act on.
            lines = [l.rstrip() for l in out.splitlines() if l.strip()]
            head = lines[0] if lines else ""
            print(f"  {n}: {head[:110]}")
            keyed = [l for l in lines[1:] if any(
                k in l.lower() for k in ("finding", "error", "fail", "missing", "does not exist",
                                         "broken", "unregistered", "drift", ".md:", ".py:", ".go:"))]
            for l in (keyed or lines[1:])[-6:]:
                print(f"      {l.strip()[:160]}")
        print("\nFix it, or add a KNOWN_RED row naming a tracked deferral. A gate that "
              "is red and unacknowledged is how a whole suite becomes background noise.")
        rc = 1
    if unexpected_green:
        print(f"\ngate-wiring-gate: {len(unexpected_green)} KNOWN_RED row(s) are STALE — "
              "the gate passes now:\n")
        for n in unexpected_green:
            print(f"  {n}  (was: {KNOWN_RED[n][0]})")
        print("\nDelete the row and close the deferral. An acknowledgement list that "
              "never shrinks stops being an acknowledgement and becomes a permanent "
              "exemption — the same reason file-ceiling-gate reds when allowlisted "
              "debt GROWS.")
        rc = 1
    return rc


def self_test() -> int:
    fails = []

    if not is_gate("foo-gate.py"):
        fails.append("did not recognise foo-gate.py as a gate")
    if not is_gate("bar-lint.sh"):
        fails.append("did not recognise bar-lint.sh as a gate")
    if is_gate("build-stack.sh"):
        fails.append("treated an ordinary script as a gate")
    if is_gate("some-gate.txt"):
        fails.append("treated a non-script as a gate")

    # L4 — the `-live-smoke` shape. Without this case, narrowing the predicate back would
    # make fifteen checks invisible again and every other assertion here would stay green:
    # the gate would report a smaller, tidier world and call it OK.
    if not is_gate("picker-search-live-smoke.sh"):
        fails.append("did not recognise a -live-smoke script as in scope")
    if not is_gate("some_live_smoke.py"):
        fails.append("did not recognise the underscore spelling of -live-smoke")
    # ...and the shape must stay a SUFFIX. `smoke-test-helpers.sh` is not a check.
    if is_gate("smoke-helpers.sh"):
        fails.append("treated a merely smoke-ish filename as a check")

    # Every live smoke discovered must carry a registry row. They cannot run on a bare
    # checkout, so an unregistered one is not "wired" — it is the absence this row closed,
    # arriving again in a file nobody has written yet.
    unregistered = [
        n for n in discovered()
        if n.rsplit("/", 1)[-1].rsplit(".", 1)[0].endswith(("-live-smoke", "_live_smoke"))
        and n not in NEEDS_STACK and n not in EXEMPT and n not in TOO_SLOW
        and n not in KNOWN_RED
    ]
    if unregistered:
        fails.append(f"live smoke(s) with no registry row: {unregistered}")

    # The scope must stay a PREDICATE. If someone replaces it with a list, a gate
    # created tomorrow is default-uncovered and this whole file is theatre.
    if isinstance(getattr(sys.modules[__name__], "is_gate", None), (list, tuple, set)):
        fails.append("is_gate is a collection, not a predicate")

    # Every EXEMPT / KNOWN_RED row must point at a file that exists, or the list
    # is describing a tree that is gone.
    _, stale = wiring_report()
    if stale:
        fails.append(f"rows for files that no longer exist: {', '.join(stale)}")

    # A MUTATES_TREE name that is not a real gate is a silent LOSS of isolation: the runner
    # would find nothing to serialise, put every gate back in the pool, and the race this set
    # exists to prevent returns with no message anywhere. Same shape as the REQUIRES_ENV orphan
    # check in guard-redability-gate, and for the same reason.
    for n in sorted(MUTATES_TREE):
        if not (REPO / n).exists():
            fails.append(f"MUTATES_TREE names {n}, which does not exist — isolation lost silently")

    # Every KNOWN_RED row must name a deferral id, or "tracked" means nothing.
    for n, (did, why) in KNOWN_RED.items():
        if not did.startswith("D-") or len(did) < 6:
            fails.append(f"{n}: KNOWN_RED row has no tracked deferral id")
        if len(why.strip()) < 20:
            fails.append(f"{n}: KNOWN_RED row has no real reason")
    for n, why in EXEMPT.items():
        if len(why.strip()) < 20:
            fails.append(f"{n}: EXEMPT row has no real reason")
    for n, why in NEEDS_STACK.items():
        if len(why.strip()) < 20:
            fails.append(f"{n}: NEEDS_STACK row has no real reason")
    for n, why in TOO_SLOW.items():
        if len(why.strip()) < 20:
            fails.append(f"{n}: TOO_SLOW row has no real reason")

    # The runner is the coverage mechanism. If it is not in CI, every gate is
    # back to needing an individual line and this file's headline claim is false.
    if not runner_in_ci():
        fails.append("no workflow invokes `gate-wiring-gate.py --run-all` — without the "
                     "runner, coverage is per-name again and a gate written tomorrow "
                     "is uncovered")

    # This gate must itself be wired, or it is the thing it exists to forbid.
    hook = _text([HOOK])
    ci = _text(sorted(WORKFLOWS.glob("*.yml")))
    me = Path(__file__).name
    if me not in hook and me not in ci:  # noqa: SIM102 — read as one condition
        fails.append(f"{me} is not wired into the hook or CI — the wiring gate is "
                     "itself unwired, which is precisely the defect it reports")

    if fails:
        print("gate-wiring-gate SELF-TEST FAILED:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("gate-wiring-gate: self-test OK — the scope is a predicate (a gate created "
          "tomorrow is covered), every exemption carries a reason, every KNOWN_RED row "
          "names a deferral, and this gate is itself wired")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-all", action="store_true",
                    help="execute every discovered gate (CI); honours KNOWN_RED")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.run_all:
        return run_all()

    unwired, stale = wiring_report()
    total = len(discovered())
    if stale:
        print("gate-wiring-gate: STALE row(s) for files that no longer exist:")
        for n in stale:
            print(f"  {n}")
        print("\nDelete them — a registry describing a tree that is gone makes the "
              "list look like it is doing more work than it is.")
        return 1
    if unwired:
        print(f"gate-wiring-gate: {len(unwired)} gate(s) run NOWHERE\n")
        for n in unwired:
            print(f"  {n}")
        print("\nA gate that is in neither .githooks/pre-commit nor .github/workflows/ "
              "does not run, and its presence in scripts/ answers \"is this covered?\" "
              "with a yes. Wire it, or add an EXEMPT row with a reason.")
        return 1
    print(f"gate-wiring-gate: OK — {total} gate(s) discovered, all wired or exempted "
          f"({len(EXEMPT)} exempt, {len(KNOWN_RED)} tracked-red)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
